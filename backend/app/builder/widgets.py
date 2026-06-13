"""Widget-Engine: wertet Dashboard-Kacheln über beliebige Datenquellen aus.

Nutzt dieselben Bausteine wie die Automationen (_iter_source_objects,
_flatten_record, check_conditions) — eine Quelle, eine Filtersprache.
"""

from sqlalchemy.orm import Session

from .automations import _flatten_record, _iter_source_objects, check_conditions
from .definitions import WidgetDef
from .models import Widget

# Quelle → Modul für die Berechtigungsprüfung
_SOURCE_MODULES = {
    "crm": "crm", "crm.customers": "crm", "crm.customer": "crm",
    "finance.invoices": "finance", "finance.invoice": "finance",
    "finance.expenses": "finance", "finance.expense": "finance",
    "projects.tasks": "projects", "projects.task": "projects",
    "hr.employees": "hr", "hr.employee": "hr",
}


def module_for_source(source: str) -> str:
    if source.startswith("custom:"):
        return source
    return _SOURCE_MODULES.get(source, source.split(".")[0])


def create_widget(db: Session, definition: WidgetDef) -> Widget:
    if definition.metric == "sum" and not definition.metric_field:
        raise ValueError("metric=sum benötigt metric_field")
    widget = Widget(
        title=definition.title,
        widget_type=definition.widget_type,
        source=definition.source,
        metric=definition.metric,
        metric_field=definition.metric_field,
        group_by=definition.group_by,
        conditions=[c.model_dump() for c in definition.conditions],
        limit=definition.limit,
    )
    db.add(widget)
    db.commit()
    return widget


def _matching_rows(db: Session, widget: Widget) -> list[dict]:
    rows = []
    for obj in _iter_source_objects(db, widget.source):
        record = _flatten_record(obj)
        context = {"event": {}, "record": record}
        if check_conditions(widget.conditions, context):
            rows.append(record)
    return rows


def _metric_value(rows: list[dict], metric: str, metric_field: str | None) -> float:
    if metric == "sum" and metric_field:
        total = 0.0
        for row in rows:
            try:
                total += float(row.get(metric_field) or 0)
            except (TypeError, ValueError):
                continue
        return round(total, 2)
    return len(rows)


def evaluate_widget(db: Session, widget: Widget) -> dict:
    rows = _matching_rows(db, widget)
    base = {
        "id": widget.id, "title": widget.title, "widget_type": widget.widget_type,
        "source": widget.source,
    }
    if widget.widget_type == "kennzahl":
        return {**base, "value": _metric_value(rows, widget.metric, widget.metric_field),
                "metric": widget.metric}
    if widget.widget_type == "diagramm":
        groups: dict[str, list[dict]] = {}
        for row in rows:
            key = str(row.get(widget.group_by) or "—")
            groups.setdefault(key, []).append(row)
        bars = [
            {"label": label, "value": _metric_value(group, widget.metric, widget.metric_field)}
            for label, group in groups.items()
        ]
        bars.sort(key=lambda b: b["value"], reverse=True)
        return {**base, "bars": bars[: widget.limit], "group_by": widget.group_by}
    # liste
    hidden = {"tenant_id", "embedding_json", "password_hash"}
    cleaned = [
        {k: v for k, v in row.items() if k not in hidden and v not in (None, "")}
        for row in rows[: widget.limit]
    ]
    return {**base, "rows": cleaned}
