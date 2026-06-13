"""Tests der Workflow-Engine: Urlaubsfreigabe über zwei Stufen."""

from backend.app.builder.definitions import WorkflowDef
from backend.tests.conftest import login
from backend.tests.test_auth_tenancy import _create_user


def _create_workflow(client, definition: dict):
    from backend.app.builder.activation import materialize
    from backend.app.core.database import SessionLocal
    from backend.app.core.tenancy import Tenant

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).first()
        db.info["tenant_id"] = tenant.id
        return materialize(db, "workflow", WorkflowDef(**definition).model_dump())
    finally:
        db.close()


URLAUB_WORKFLOW = {
    "name": "Urlaubsfreigabe",
    "description": "Urlaub: erst Geschäftsführung, dann Buchhaltung (Abrechnung)",
    "trigger_event": "hr.absence.created",
    "steps": [
        {"name": "Freigabe Geschäftsführung", "approver_role": "Geschäftsführung"},
        {"name": "Erfassung Buchhaltung", "approver_role": "Buchhaltung"},
    ],
}


def _start_instance(client) -> dict:
    employee = client.post("/api/hr/employees", json={
        "first_name": "Tina", "last_name": "Test",
    }).json()
    client.post(f"/api/hr/employees/{employee['id']}/absences", json={
        "kind": "urlaub", "start_date": "2026-08-01", "end_date": "2026-08-14",
    })
    instances = client.get("/api/workflows/instances").json()
    assert instances, "Workflow-Instanz muss durch das Event entstehen"
    return instances[0]


def test_workflow_two_step_approval(client):
    _create_workflow(client, URLAUB_WORKFLOW)
    instance = _start_instance(client)
    assert instance["status"] == "offen"
    assert instance["current_approver_role"] == "Geschäftsführung"
    assert "urlaub" in instance["subject_summary"]

    _create_user(client, "gf@testfirma.de", "Geschäftsführung")
    _create_user(client, "buch@testfirma.de", "Buchhaltung")
    gf = {"Authorization": f"Bearer {login(client, 'gf@testfirma.de', 'geheim123')}"}
    buch = {"Authorization": f"Bearer {login(client, 'buch@testfirma.de', 'geheim123')}"}

    # Falsche Rolle darf nicht entscheiden
    wrong = client.post(f"/api/workflows/instances/{instance['id']}/decide",
                        headers=buch, json={"decision": "genehmigt"})
    assert wrong.status_code == 403

    # GF sieht den Vorgang in der Inbox, Buchhaltung (noch) nicht
    assert len(client.get("/api/workflows/inbox", headers=gf).json()) == 1
    assert client.get("/api/workflows/inbox", headers=buch).json() == []

    # Stufe 1: GF genehmigt → Stufe 2
    step1 = client.post(f"/api/workflows/instances/{instance['id']}/decide",
                        headers=gf, json={"decision": "genehmigt", "comment": "Passt."})
    assert step1.json()["current_step"] == 1
    assert step1.json()["current_approver_role"] == "Buchhaltung"

    # Buchhaltung wurde benachrichtigt
    notes = client.get("/api/notifications", headers=buch).json()
    assert any("Urlaubsfreigabe" in n["message"] for n in notes)

    # Stufe 2: Buchhaltung genehmigt → abgeschlossen
    step2 = client.post(f"/api/workflows/instances/{instance['id']}/decide",
                        headers=buch, json={"decision": "genehmigt"})
    assert step2.json()["status"] == "genehmigt"
    assert len(step2.json()["approvals"]) == 2

    # Abgeschlossene Vorgänge sind nicht erneut entscheidbar
    again = client.post(f"/api/workflows/instances/{instance['id']}/decide",
                        headers=buch, json={"decision": "abgelehnt"})
    assert again.status_code == 409


def test_workflow_rejection_stops_process(client):
    _create_workflow(client, URLAUB_WORKFLOW)
    instance = _start_instance(client)

    _create_user(client, "gf2@testfirma.de", "Geschäftsführung")
    gf = {"Authorization": f"Bearer {login(client, 'gf2@testfirma.de', 'geheim123')}"}
    rejected = client.post(f"/api/workflows/instances/{instance['id']}/decide",
                           headers=gf, json={"decision": "abgelehnt", "comment": "Engpass im August."})
    assert rejected.json()["status"] == "abgelehnt"


def test_workflow_requires_existing_role(client):
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _create_workflow(client, {**URLAUB_WORKFLOW, "steps": [
            {"name": "Freigabe", "approver_role": "Phantomrolle"},
        ]})
    assert exc.value.status_code == 422


def test_workflow_completion_can_trigger_automation(client):
    """Workflows und Automationen verketten sich über den Event-Bus."""
    from backend.tests.test_automations import _create_automation

    _create_workflow(client, URLAUB_WORKFLOW)
    _create_automation(client, {
        "name": "Genehmigten Urlaub melden",
        "trigger_type": "event",
        "trigger_event": "workflow.instance.completed",
        "conditions": [{"field": "status", "op": "eq", "value": "genehmigt"}],
        "actions": [{"action_type": "notify", "notify_role": "Admin",
                     "message": "{{event.workflow}}: {{event.subject_ref}} wurde genehmigt."}],
    })

    instance = _start_instance(client)
    _create_user(client, "gf3@testfirma.de", "Geschäftsführung")
    _create_user(client, "buch3@testfirma.de", "Buchhaltung")
    gf = {"Authorization": f"Bearer {login(client, 'gf3@testfirma.de', 'geheim123')}"}
    buch = {"Authorization": f"Bearer {login(client, 'buch3@testfirma.de', 'geheim123')}"}
    client.post(f"/api/workflows/instances/{instance['id']}/decide",
                headers=gf, json={"decision": "genehmigt"})
    client.post(f"/api/workflows/instances/{instance['id']}/decide",
                headers=buch, json={"decision": "genehmigt"})

    notes = client.get("/api/notifications").json()  # Admin-Sicht
    assert any("wurde genehmigt" in n["message"] for n in notes)
