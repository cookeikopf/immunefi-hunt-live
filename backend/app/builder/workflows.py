"""Workflow-Engine: mehrstufige Genehmigungen.

Statusmaschine: offen (Stufe 0..n) → genehmigt | abgelehnt.
Eine Instanz entsteht event-getrieben (z. B. 'hr.absence.created');
jede Stufe wird von einer Rolle entschieden. Abschluss publiziert
'workflow.instance.completed' — verkettbar mit Automationen.
"""

import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..core import events
from ..core.database import SessionLocal
from ..modules.auth.models import Role, User
from .automations import _flatten_record, _load_trigger_object
from .definitions import WorkflowDef
from .models import Notification, WorkflowApproval, WorkflowDefinition, WorkflowInstance

logger = logging.getLogger(__name__)


def create_workflow(db: Session, definition: WorkflowDef) -> WorkflowDefinition:
    existing_roles = {r.name for r in db.query(Role).all()}
    for step in definition.steps:
        if step.approver_role not in existing_roles:
            raise HTTPException(
                422, f"Rolle '{step.approver_role}' existiert nicht — "
                     f"vorhanden: {sorted(existing_roles)}")
    workflow = WorkflowDefinition(
        name=definition.name,
        description=definition.description,
        trigger_event=definition.trigger_event,
        steps=[s.model_dump() for s in definition.steps],
    )
    db.add(workflow)
    db.commit()
    return workflow


def _notify_role(db: Session, tenant_id: int, role_name: str, message: str, source: str) -> None:
    db.add(Notification(tenant_id=tenant_id, role_name=role_name,
                        message=message, source=source))


def _on_event(event: str, payload: dict[str, Any]) -> None:
    tenant_id = payload.get("tenant_id")
    if tenant_id is None or "id" not in payload:
        return
    db = SessionLocal()
    db.info["tenant_id"] = tenant_id
    try:
        definitions = (
            db.query(WorkflowDefinition)
            .filter(WorkflowDefinition.active.is_(True),
                    WorkflowDefinition.trigger_event == event)
            .all()
        )
        if not definitions:
            return
        subject = _load_trigger_object(db, event, payload)
        summary_lines = [
            f"{key}: {value}" for key, value in _flatten_record(subject).items()
            if value not in (None, "") and key not in ("tenant_id", "embedding_json")
        ]
        subject_ref = f"{event.rsplit('.', 1)[0]}:{payload['id']}"
        for definition in definitions:
            instance = WorkflowInstance(
                definition_id=definition.id,
                subject_ref=subject_ref,
                subject_summary="\n".join(summary_lines) or subject_ref,
            )
            db.add(instance)
            first_role = definition.steps[0]["approver_role"]
            _notify_role(db, tenant_id, first_role,
                         f"Neue Genehmigung wartet: {definition.name} ({subject_ref})",
                         f"Workflow: {definition.name}")
        db.commit()
    except Exception:
        logger.exception("Workflow-Start für Event %s fehlgeschlagen", event)
    finally:
        db.close()


def register_workflow_handlers() -> None:
    events.subscribe("*", _on_event)


def decide(db: Session, user: User, instance: WorkflowInstance,
           decision: str, comment: str | None) -> WorkflowInstance:
    if instance.status != "offen":
        raise HTTPException(409, f"Vorgang ist bereits {instance.status}")
    if decision not in ("genehmigt", "abgelehnt"):
        raise HTTPException(422, "decision muss 'genehmigt' oder 'abgelehnt' sein")

    step = instance.definition.steps[instance.current_step]
    if user.role.name not in (step["approver_role"], "Admin"):
        raise HTTPException(
            403, f"Diese Stufe ('{step['name']}') entscheidet die Rolle "
                 f"'{step['approver_role']}'")

    db.add(WorkflowApproval(
        instance_id=instance.id,
        step_index=instance.current_step,
        decision=decision,
        decided_by=user.id,
        comment=comment,
    ))

    tenant_id = db.info.get("tenant_id")
    if decision == "abgelehnt":
        instance.status = "abgelehnt"
    elif instance.current_step + 1 >= len(instance.definition.steps):
        instance.status = "genehmigt"
    else:
        instance.current_step += 1
        next_role = instance.definition.steps[instance.current_step]["approver_role"]
        _notify_role(db, tenant_id, next_role,
                     f"Genehmigung wartet (Stufe {instance.current_step + 1}): "
                     f"{instance.definition.name} ({instance.subject_ref})",
                     f"Workflow: {instance.definition.name}")
    db.commit()

    if instance.status in ("genehmigt", "abgelehnt"):
        events.publish("workflow.instance.completed", {
            "tenant_id": tenant_id, "id": instance.id,
            "status": instance.status, "subject_ref": instance.subject_ref,
            "workflow": instance.definition.name,
        })
    return instance


def inbox(db: Session, user: User) -> list[WorkflowInstance]:
    """Offene Vorgänge, deren aktuelle Stufe der Benutzer entscheiden darf."""
    open_instances = (
        db.query(WorkflowInstance)
        .filter(WorkflowInstance.status == "offen")
        .order_by(WorkflowInstance.created_at)
        .all()
    )
    return [
        instance for instance in open_instances
        if user.role.name in (
            instance.definition.steps[instance.current_step]["approver_role"], "Admin")
    ]
