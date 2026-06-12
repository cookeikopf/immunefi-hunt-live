"""Tests der Automationen-Engine: Event-Trigger, Bedingungen, Aktionen,
zeitgesteuerte Prüfungen mit Dedup, Mitteilungen."""

from datetime import datetime, timedelta, timezone

from backend.app.builder.automations import run_scheduled
from backend.app.builder.definitions import AutomationDef
from backend.tests.test_builder_modules import FUHRPARK


def _create_automation(client, definition: dict):
    """Legt eine Automation über den Draft-Weg an (wie aktivierte KI-Entwürfe)."""
    from backend.app.builder.activation import materialize
    from backend.app.core.database import SessionLocal
    from backend.app.core.tenancy import Tenant

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).first()
        db.info["tenant_id"] = tenant.id
        return materialize(db, "automation", AutomationDef(**definition).model_dump())
    finally:
        db.close()


def test_event_automation_with_condition_creates_task_and_notification(client):
    _create_automation(client, {
        "name": "Großrechnung melden",
        "trigger_type": "event",
        "trigger_event": "finance.invoice.created",
        "conditions": [{"field": "amount_net", "op": "gt", "value": 5000}],
        "actions": [
            {"action_type": "create_record", "target": "projects.task",
             "values": {"title": "Rechnung {{record.number}} prüfen ({{record.amount_net}} EUR)"}},
            {"action_type": "notify", "notify_role": "Geschäftsführung",
             "message": "Große Rechnung {{record.number}} über {{record.amount_net}} EUR erstellt."},
        ],
    })

    # Kleine Rechnung: Bedingung greift nicht
    client.post("/api/finance/invoices", json={
        "number": "RE-K1", "amount_net": 100, "issue_date": "2026-06-01",
    })
    projects = client.get("/api/projects").json()
    assert all(not p["tasks"] for p in projects)

    # Große Rechnung: Aufgabe + Mitteilung entstehen
    client.post("/api/finance/invoices", json={
        "number": "RE-G1", "amount_net": 12000, "issue_date": "2026-06-01",
    })
    projects = client.get("/api/projects").json()
    intern = next(p for p in projects if p["name"] == "Interne Aufgaben")
    assert any("RE-G1" in t["title"] for t in intern["tasks"])

    # Mitteilung für Geschäftsführung sichtbar (Admin sieht über Rolle nicht,
    # daher als GF-Benutzer prüfen)
    from backend.tests.conftest import login
    from backend.tests.test_auth_tenancy import _create_user

    _create_user(client, "gf@testfirma.de", "Geschäftsführung")
    headers = {"Authorization": f"Bearer {login(client, 'gf@testfirma.de', 'geheim123')}"}
    notes = client.get("/api/notifications", headers=headers).json()
    assert any("RE-G1" in n["message"] for n in notes)

    # Ausführungsprotokoll vorhanden
    automations = client.get("/api/builder/automations").json()
    runs = client.get(f"/api/builder/automations/{automations[0]['id']}/runs").json()
    assert len(runs) == 1 and runs[0]["status"] == "ok"


def test_scheduled_automation_over_source_with_dedup(client):
    client.post("/api/builder/modules", json=FUHRPARK)
    client.post("/api/custom/fuhrpark/records", json={
        "kennzeichen": "S-TÜV 1", "tuev_datum": "2020-01-01",  # längst überfällig
    })
    client.post("/api/custom/fuhrpark/records", json={
        "kennzeichen": "S-OK 2", "tuev_datum": "2099-01-01",
    })

    _create_automation(client, {
        "name": "TÜV-Prüfung",
        "trigger_type": "schedule",
        "schedule": "daily@06:00",
        "source": "custom:fuhrpark",
        "conditions": [{"field": "tuev_datum", "op": "lt", "value": "{{today}}"}],
        "actions": [{"action_type": "create_record", "target": "projects.task",
                     "values": {"title": "TÜV fällig: {{record.kennzeichen}}"}}],
    })

    # Fälligkeit erzwingen und Tick direkt ausführen
    from backend.app.builder.models import Automation
    from backend.app.core.database import SessionLocal

    db = SessionLocal()
    db.query(Automation).update(
        {"next_run_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
    db.commit(); db.close()

    assert run_scheduled() == 1

    projects = client.get("/api/projects").json()
    intern = next(p for p in projects if p["name"] == "Interne Aufgaben")
    titles = [t["title"] for t in intern["tasks"]]
    assert "TÜV fällig: S-TÜV 1" in titles
    assert not any("S-OK 2" in t for t in titles)

    # Zweiter Lauf: Dedup verhindert doppelte Aufgaben
    db = SessionLocal()
    db.query(Automation).update(
        {"next_run_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
    db.commit(); db.close()
    run_scheduled()
    projects = client.get("/api/projects").json()
    intern = next(p for p in projects if p["name"] == "Interne Aufgaben")
    assert [t["title"] for t in intern["tasks"]].count("TÜV fällig: S-TÜV 1") == 1


def test_automation_toggle(client):
    _create_automation(client, {
        "name": "Lead-Begrüßung",
        "trigger_type": "event",
        "trigger_event": "crm.customer.created",
        "actions": [{"action_type": "notify", "notify_role": "Admin",
                     "message": "Neuer Kunde angelegt"}],
    })
    automation = client.get("/api/builder/automations").json()[0]
    client.patch(f"/api/builder/automations/{automation['id']}?active=false")

    client.post("/api/crm/customers", json={"name": "Stiller Kunde"})
    runs = client.get(f"/api/builder/automations/{automation['id']}/runs").json()
    assert runs == []
