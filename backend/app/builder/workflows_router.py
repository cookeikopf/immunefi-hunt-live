"""Workflow-API: Definitionen, Vorgänge, Inbox, Entscheidung."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..modules.auth.deps import get_current_user, get_tenant_db, require_module
from ..modules.auth.models import User
from .models import WorkflowDefinition, WorkflowInstance
from .workflows import decide, inbox

router = APIRouter(
    prefix="/api/workflows", dependencies=[Depends(require_module("workflows"))],
    tags=["Workflows"],
)


class DecisionRequest(BaseModel):
    decision: str  # genehmigt | abgelehnt
    comment: str | None = None


def _definition_out(definition: WorkflowDefinition) -> dict:
    return {
        "id": definition.id, "name": definition.name,
        "description": definition.description,
        "trigger_event": definition.trigger_event,
        "steps": definition.steps, "active": definition.active,
    }


def _instance_out(instance: WorkflowInstance) -> dict:
    steps = instance.definition.steps
    return {
        "id": instance.id,
        "workflow": instance.definition.name,
        "subject_ref": instance.subject_ref,
        "subject_summary": instance.subject_summary,
        "status": instance.status,
        "current_step": instance.current_step,
        "current_step_name": steps[instance.current_step]["name"]
        if instance.status == "offen" else None,
        "current_approver_role": steps[instance.current_step]["approver_role"]
        if instance.status == "offen" else None,
        "steps_total": len(steps),
        "approvals": [
            {"step_index": a.step_index, "decision": a.decision,
             "comment": a.comment, "created_at": a.created_at}
            for a in instance.approvals
        ],
        "created_at": instance.created_at,
    }


@router.get("/definitions")
def list_definitions(db: Session = Depends(get_tenant_db)):
    return [_definition_out(d) for d in
            db.query(WorkflowDefinition).order_by(WorkflowDefinition.name).all()]


@router.patch("/definitions/{definition_id}")
def toggle_definition(definition_id: int, active: bool, db: Session = Depends(get_tenant_db)):
    definition = db.query(WorkflowDefinition).filter(
        WorkflowDefinition.id == definition_id).first()
    if definition is None:
        raise HTTPException(404, "Workflow nicht gefunden")
    definition.active = active
    db.commit()
    return _definition_out(definition)


@router.get("/instances")
def list_instances(status: str | None = None, db: Session = Depends(get_tenant_db)):
    query = db.query(WorkflowInstance).order_by(WorkflowInstance.created_at.desc())
    if status:
        query = query.filter(WorkflowInstance.status == status)
    return [_instance_out(i) for i in query.limit(100).all()]


@router.get("/inbox")
def my_inbox(user: User = Depends(get_current_user), db: Session = Depends(get_tenant_db)):
    return [_instance_out(i) for i in inbox(db, user)]


@router.post("/instances/{instance_id}/decide")
def decide_instance(
    instance_id: int,
    request: DecisionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    instance = db.query(WorkflowInstance).filter(WorkflowInstance.id == instance_id).first()
    if instance is None:
        raise HTTPException(404, "Vorgang nicht gefunden")
    return _instance_out(decide(db, user, instance, request.decision, request.comment))
