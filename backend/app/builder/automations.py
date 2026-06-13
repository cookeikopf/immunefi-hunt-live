"""Automationen-Engine: Wenn-Dann-Regeln ausführen.

Zwei Trigger-Arten:
- event:    Der Dispatcher abonniert den Event-Bus; bei passendem Event
            werden Bedingungen gegen Event + auslösendes Objekt geprüft.
- schedule: Der Scheduler (scheduler.py) ruft run_scheduled() auf;
            optional wird eine Datenquelle Eintrag für Eintrag geprüft
            (z. B. "täglich: TÜV-Datum überschritten → Aufgabe"), mit
            Dedup über AutomationRun.target_ref.

Aktionen: create_record (Aufgabe, Kundennotiz, Custom-Record),
update_record (auslösendes Objekt ändern), notify (interne Mitteilung).
Template-Variablen: {{event.<key>}}, {{record.<feld>}}, {{today}}.
"""

import logging
import re
import threading
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..core import events
from ..core.database import SessionLocal
from .definitions import AutomationDef
from .models import Automation, AutomationRun, CustomModule, CustomRecord, Notification

logger = logging.getLogger(__name__)

_local = threading.local()
MAX_DEPTH = 3  # Rekursionsschutz: Automation löst Automation aus


# ---- Anlegen ----

def _next_run(schedule: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(timezone.utc)
    if schedule.startswith("every:") and schedule.endswith("m"):
        minutes = int(schedule[len("every:"):-1])
        return now + timedelta(minutes=max(1, minutes))
    if schedule.startswith("daily@"):
        hour, minute = (int(x) for x in schedule[len("daily@"):].split(":"))
        candidate = datetime.combine(now.date(), time(hour, minute, tzinfo=timezone.utc))
        return candidate if candidate > now else candidate + timedelta(days=1)
    raise ValueError(f"Unbekanntes Zeitplan-Format: {schedule}")


def create_automation(db: Session, definition: AutomationDef) -> Automation:
    if definition.trigger_type == "event" and not definition.trigger_event:
        raise ValueError("trigger_event fehlt für trigger_type=event")
    if definition.trigger_type == "schedule" and not definition.schedule:
        raise ValueError("schedule fehlt für trigger_type=schedule")
    automation = Automation(
        name=definition.name,
        trigger_type=definition.trigger_type,
        trigger_event=definition.trigger_event,
        schedule=definition.schedule,
        source=definition.source,
        conditions=[c.model_dump() for c in definition.conditions],
        actions=[a.model_dump() for a in definition.actions],
        next_run_at=_next_run(definition.schedule) if definition.trigger_type == "schedule" else None,
    )
    db.add(automation)
    db.commit()
    return automation


# ---- Kontext & Bedingungen ----

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _flatten_record(obj: Any) -> dict:
    """Macht aus dem auslösenden Objekt ein flaches Feld→Wert-Dict."""
    if obj is None:
        return {}
    if isinstance(obj, CustomRecord):
        return dict(obj.values)
    data = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name, None)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        data[column.name] = value
    return data


def _resolve(context: dict, path: str):
    if path == "today":
        return date.today().isoformat()
    parts = path.split(".", 1)
    scope = context.get(parts[0], {})
    if len(parts) == 1:
        return scope
    return scope.get(parts[1]) if isinstance(scope, dict) else None


def render_template(text: str, context: dict) -> str:
    def replace(match: re.Match) -> str:
        value = _resolve(context, match.group(1))
        return "" if value is None else str(value)

    return _TEMPLATE_RE.sub(replace, text)


def _coerce(value):
    """'{{today}}'-Ersetzung + Zahlen-Normalisierung für Vergleiche."""
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def check_conditions(conditions: list[dict], context: dict) -> bool:
    record = context.get("record", {})
    event_data = context.get("event", {})
    for condition in conditions:
        field, op = condition["field"], condition["op"]
        raw_expected = condition.get("value")
        if isinstance(raw_expected, str) and "{{" in raw_expected:
            raw_expected = render_template(raw_expected, context)
        actual = record.get(field, event_data.get(field, event_data.get(f"values.{field}")))

        if op == "is_empty":
            if actual not in (None, ""):
                return False
            continue
        if op == "not_empty":
            if actual in (None, ""):
                return False
            continue
        if actual is None:
            return False
        if op == "contains":
            if str(raw_expected).lower() not in str(actual).lower():
                return False
            continue
        left, right = _coerce(actual), _coerce(raw_expected)
        try:
            result = {
                "eq": left == right, "ne": left != right,
                "gt": left > right, "lt": left < right,
                "gte": left >= right, "lte": left <= right,
            }[op]
        except TypeError:
            result = {
                "eq": str(left) == str(right), "ne": str(left) != str(right),
                "gt": str(left) > str(right), "lt": str(left) < str(right),
                "gte": str(left) >= str(right), "lte": str(left) <= str(right),
            }[op]
        if not result:
            return False
    return True


# ---- Aktionen ----

def _render_values(values: dict[str, str], context: dict) -> dict:
    return {key: render_template(str(value), context) for key, value in values.items()}


def _get_or_create_default_project(db: Session):
    from ..modules.projects.models import Project

    project = db.query(Project).filter(Project.name == "Interne Aufgaben").first()
    if project is None:
        project = Project(name="Interne Aufgaben", status="aktiv",
                          description="Automatisch erzeugte Aufgaben aus Automationen.")
        db.add(project)
        db.flush()
    return project


def _action_create_record(db: Session, action: dict, context: dict, tenant_id: int) -> str:
    target = action.get("target") or ""
    values = _render_values(action.get("values", {}), context)

    if target in ("projects.task", "task", "aufgabe"):
        from ..modules.projects.models import Task

        project_id = values.pop("project_id", None)
        project_id = int(project_id) if project_id else _get_or_create_default_project(db).id
        task = Task(
            project_id=project_id,
            title=values.get("title") or values.get("titel") or "Automatische Aufgabe",
            due_date=date.fromisoformat(values["due_date"]) if values.get("due_date") else None,
        )
        db.add(task)
        db.commit()
        events.publish("projects.task.created",
                       {"tenant_id": tenant_id, "id": task.id, "project_id": project_id})
        return f"Aufgabe #{task.id} erstellt"

    if target in ("crm.interaction", "interaction"):
        from ..modules.crm.models import Interaction

        customer_id = values.get("customer_id")
        if not customer_id:
            raise ValueError("crm.interaction benötigt values.customer_id")
        interaction = Interaction(
            customer_id=int(customer_id),
            kind=values.get("kind", "notiz"),
            summary=values.get("summary") or values.get("message", ""),
        )
        db.add(interaction)
        db.commit()
        events.publish("crm.interaction.created",
                       {"tenant_id": tenant_id, "id": interaction.id,
                        "customer_id": interaction.customer_id})
        return f"Kundennotiz #{interaction.id} erstellt"

    if target.startswith("custom:"):
        from .records import get_module, validate_values

        slug = target.split(":", 1)[1]
        module = get_module(db, slug)
        if module is None:
            raise ValueError(f"Custom-Modul '{slug}' nicht gefunden")
        clean = validate_values(module, values)
        record = CustomRecord(module_id=module.id, values=clean)
        db.add(record)
        db.commit()
        events.publish(f"custom.{slug}.record.created",
                       {"tenant_id": tenant_id, "id": record.id, "slug": slug,
                        **{f"values.{k}": v for k, v in clean.items()}})
        return f"{module.name} #{record.id} erstellt"

    raise ValueError(f"Unbekanntes Ziel für create_record: '{target}'")


def _action_update_record(db: Session, action: dict, context: dict, tenant_id: int) -> str:
    """Ändert das auslösende Objekt (Felder aus values)."""
    obj = context.get("_object")
    if obj is None:
        raise ValueError("update_record benötigt ein auslösendes Objekt")
    values = _render_values(action.get("values", {}), context)
    if isinstance(obj, CustomRecord):
        from .records import get_module, validate_values

        module = db.query(CustomModule).filter(CustomModule.id == obj.module_id).first()
        clean = validate_values(module, {**obj.values, **values})
        obj.values = clean
    else:
        for key, value in values.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
    db.commit()
    return f"{type(obj).__name__} aktualisiert"


def _action_notify(db: Session, action: dict, context: dict, tenant_id: int, source: str) -> str:
    message = render_template(action.get("message") or "Automation ausgelöst", context)
    db.add(Notification(
        tenant_id=tenant_id,
        role_name=action.get("notify_role") or "Admin",
        message=message,
        source=source,
    ))
    db.commit()
    return "Mitteilung erstellt"


def execute_actions(db: Session, automation: Automation, context: dict,
                    tenant_id: int, target_ref: str | None = None) -> None:
    # Name/ID vor möglichen Flush-Fehlern sichern (Instanz kann expiren)
    automation_id, automation_name = automation.id, automation.name
    actions = list(automation.actions)
    details = []
    status = "ok"
    try:
        for action in actions:
            action_type = action.get("action_type")
            if action_type == "create_record":
                details.append(_action_create_record(db, action, context, tenant_id))
            elif action_type == "update_record":
                details.append(_action_update_record(db, action, context, tenant_id))
            elif action_type == "notify":
                details.append(_action_notify(db, action, context, tenant_id,
                                              f"Automation: {automation_name}"))
            else:
                raise ValueError(f"Unbekannte Aktion: {action_type}")
    except Exception as exc:
        db.rollback()  # Session nach Flush-Fehlern wieder benutzbar machen
        status = "fehler"
        details.append(str(exc))
        logger.exception("Automation '%s' fehlgeschlagen", automation_name)
    db.add(AutomationRun(
        tenant_id=tenant_id,
        automation_id=automation_id,
        trigger_info=context.get("_trigger"),
        target_ref=target_ref,
        status=status,
        detail="; ".join(details)[:2000],
    ))
    db.commit()


# ---- Event-Dispatcher ----

_EVENT_MODELS: dict[str, Any] = {}


def _load_event_models():
    if _EVENT_MODELS:
        return _EVENT_MODELS
    from ..modules.crm.models import Customer, Interaction
    from ..modules.finance.models import Expense, Invoice
    from ..modules.hr.models import Absence, Employee
    from ..modules.knowledge.models import KnowledgeDocument
    from ..modules.projects.models import Project, Task

    _EVENT_MODELS.update({
        "crm.customer": Customer, "crm.interaction": Interaction,
        "finance.invoice": Invoice, "finance.expense": Expense,
        "hr.employee": Employee, "hr.absence": Absence,
        "projects.project": Project, "projects.task": Task,
        "knowledge.document": KnowledgeDocument,
    })
    return _EVENT_MODELS


def _load_trigger_object(db: Session, event: str, payload: dict):
    if event.startswith("custom.") and ".record." in event:
        return db.query(CustomRecord).filter(CustomRecord.id == payload.get("id")).first()
    prefix = event.rsplit(".", 1)[0]
    model = _load_event_models().get(prefix)
    if model is None or "id" not in payload:
        return None
    return db.query(model).filter(model.id == payload["id"]).first()


def _dispatch(event: str, payload: dict[str, Any]) -> None:
    tenant_id = payload.get("tenant_id")
    if tenant_id is None:
        return
    if event.rsplit(".", 1)[-1] not in ("created", "updated", "deleted", "completed"):
        return

    depth = getattr(_local, "depth", 0)
    if depth >= MAX_DEPTH:
        logger.warning("Automations-Rekursionslimit erreicht bei Event %s", event)
        return

    db = SessionLocal()
    db.info["tenant_id"] = tenant_id
    try:
        automations = (
            db.query(Automation)
            .filter(Automation.active.is_(True),
                    Automation.trigger_type == "event",
                    Automation.trigger_event == event)
            .all()
        )
        if not automations:
            return
        trigger_object = _load_trigger_object(db, event, payload)
        context = {
            "event": payload,
            "record": _flatten_record(trigger_object),
            "_object": trigger_object,
            "_trigger": event,
        }
        _local.depth = depth + 1
        try:
            for automation in automations:
                if check_conditions(automation.conditions, context):
                    execute_actions(db, automation, context, tenant_id)
        finally:
            _local.depth = depth
    finally:
        db.close()


def register_automation_handlers() -> None:
    events.subscribe("*", _dispatch)


# ---- Zeitgesteuerte Ausführung (vom Scheduler aufgerufen) ----

def _iter_source_objects(db: Session, source: str):
    if source.startswith("custom:"):
        from .records import get_module

        module = get_module(db, source.split(":", 1)[1])
        if module is None:
            return []
        return db.query(CustomRecord).filter(CustomRecord.module_id == module.id).all()
    aliases = {
        "finance.invoices": "finance.invoice", "finance.expenses": "finance.expense",
        "projects.tasks": "projects.task", "crm.customers": "crm.customer",
        "hr.employees": "hr.employee", "crm": "crm.customer",
    }
    model = _load_event_models().get(aliases.get(source, source))
    return db.query(model).all() if model is not None else []


def run_scheduled(now: datetime | None = None) -> int:
    """Führt alle fälligen zeitgesteuerten Automationen aus (alle Mandanten).

    Liefert die Anzahl ausgeführter Automationen — auch direkt testbar,
    ohne auf den asyncio-Tick zu warten.
    """
    now = now or datetime.now(timezone.utc)
    _load_event_models()  # alle Mapper laden (wichtig bei Standalone-Aufrufen)
    executed = 0
    db = SessionLocal()  # bewusst ungescoped: über alle Mandanten iterieren
    try:
        due = (
            db.query(Automation)
            .filter(Automation.active.is_(True),
                    Automation.trigger_type == "schedule",
                    Automation.next_run_at.isnot(None),
                    Automation.next_run_at <= now)
            .all()
        )
        for automation in due:
            tenant_db = SessionLocal()
            tenant_db.info["tenant_id"] = automation.tenant_id
            try:
                scoped = tenant_db.query(Automation).filter(
                    Automation.id == automation.id).first()
                if automation.source:
                    for obj in _iter_source_objects(tenant_db, automation.source):
                        target_ref = f"{automation.source}:{obj.id}"
                        already = tenant_db.query(AutomationRun).filter(
                            AutomationRun.automation_id == automation.id,
                            AutomationRun.target_ref == target_ref,
                            AutomationRun.status == "ok",
                        ).first()
                        if already:
                            continue
                        context = {
                            "event": {}, "record": _flatten_record(obj),
                            "_object": obj, "_trigger": f"schedule:{automation.schedule}",
                        }
                        if check_conditions(scoped.conditions, context):
                            execute_actions(tenant_db, scoped, context,
                                            automation.tenant_id, target_ref=target_ref)
                else:
                    context = {"event": {}, "record": {}, "_object": None,
                               "_trigger": f"schedule:{automation.schedule}"}
                    if check_conditions(scoped.conditions, context):
                        execute_actions(tenant_db, scoped, context, automation.tenant_id)
                scoped.next_run_at = _next_run(automation.schedule, now)
                tenant_db.commit()
                executed += 1
            finally:
                tenant_db.close()
    finally:
        db.close()
    return executed
