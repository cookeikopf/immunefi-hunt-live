"""Tests der Widget-Engine: Kennzahl, Summe, Diagramm, Berechtigungsfilter."""

from backend.app.builder.definitions import WidgetDef
from backend.tests.conftest import login
from backend.tests.test_auth_tenancy import _create_user


def _create_widget(client, definition: dict):
    from backend.app.builder.activation import materialize
    from backend.app.core.database import SessionLocal
    from backend.app.core.tenancy import Tenant

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).first()
        db.info["tenant_id"] = tenant.id
        return materialize(db, "widget", WidgetDef(**definition).model_dump())
    finally:
        db.close()


def _seed_invoices(client):
    for number, amount, status in [
        ("RE-1", 1000, "offen"), ("RE-2", 2500, "offen"), ("RE-3", 4000, "bezahlt"),
    ]:
        client.post("/api/finance/invoices", json={
            "number": number, "amount_net": amount,
            "issue_date": "2026-06-01", "status": status,
        })


def test_kennzahl_and_diagramm_widgets(client):
    _seed_invoices(client)
    _create_widget(client, {
        "title": "Offener Umsatz",
        "widget_type": "kennzahl",
        "source": "finance.invoices",
        "metric": "sum", "metric_field": "amount_net",
        "conditions": [{"field": "status", "op": "eq", "value": "offen"}],
    })
    _create_widget(client, {
        "title": "Rechnungen nach Status",
        "widget_type": "diagramm",
        "source": "finance.invoices",
        "group_by": "status",
    })
    _create_widget(client, {
        "title": "Offene Rechnungen",
        "widget_type": "liste",
        "source": "finance.invoices",
        "conditions": [{"field": "status", "op": "eq", "value": "offen"}],
        "limit": 5,
    })

    data = client.get("/api/custom/widgets/data").json()
    assert len(data) == 3

    kennzahl = next(w for w in data if w["widget_type"] == "kennzahl")
    assert kennzahl["value"] == 3500.0

    diagramm = next(w for w in data if w["widget_type"] == "diagramm")
    bars = {b["label"]: b["value"] for b in diagramm["bars"]}
    assert bars == {"offen": 2, "bezahlt": 1}

    liste = next(w for w in data if w["widget_type"] == "liste")
    assert len(liste["rows"]) == 2
    assert all(r["status"] == "offen" for r in liste["rows"])


def test_widget_data_respects_source_permissions(client):
    _seed_invoices(client)
    _create_widget(client, {
        "title": "Umsatz gesamt", "widget_type": "kennzahl",
        "source": "finance.invoices", "metric": "sum", "metric_field": "amount_net",
    })
    _create_widget(client, {
        "title": "Projekte", "widget_type": "kennzahl", "source": "projects.tasks",
    })

    # Mitarbeiter darf finance nicht lesen → sieht nur das Projekt-Widget
    _create_user(client, "wid@testfirma.de", "Mitarbeiter")
    headers = {"Authorization": f"Bearer {login(client, 'wid@testfirma.de', 'geheim123')}"}
    data = client.get("/api/custom/widgets/data", headers=headers).json()
    assert [w["title"] for w in data] == ["Projekte"]

    # Admin sieht beide
    assert len(client.get("/api/custom/widgets/data").json()) == 2


def test_widget_over_custom_module(client):
    from backend.tests.test_builder_modules import FUHRPARK

    client.post("/api/builder/modules", json=FUHRPARK)
    for kennzeichen, status in [("S-A 1", "werkstatt"), ("S-B 2", "verfügbar"), ("S-C 3", "werkstatt")]:
        client.post("/api/custom/fuhrpark/records", json={
            "kennzeichen": kennzeichen, "status": status,
        })
    _create_widget(client, {
        "title": "Fahrzeuge in der Werkstatt", "widget_type": "kennzahl",
        "source": "custom:fuhrpark",
        "conditions": [{"field": "status", "op": "eq", "value": "werkstatt"}],
    })
    data = client.get("/api/custom/widgets/data").json()
    assert data[0]["value"] == 2

    # Widget-Verwaltung: löschen
    widgets = client.get("/api/builder/widgets").json()
    client.delete(f"/api/builder/widgets/{widgets[0]['id']}")
    assert client.get("/api/custom/widgets/data").json() == []
