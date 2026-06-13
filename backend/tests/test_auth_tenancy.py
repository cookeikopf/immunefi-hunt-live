"""Tests für Setup, Login, Berechtigungen und Mandanten-Isolation."""

from backend.tests.conftest import ADMIN, login


def test_setup_flow_and_login(anon_client):
    status = anon_client.get("/api/setup/status").json()
    assert status["needs_setup"] is True

    created = anon_client.post("/api/setup", json=ADMIN)
    assert created.status_code == 201
    assert created.json()["user"]["role"] == "Admin"

    # Setup nur einmal möglich
    assert anon_client.post("/api/setup", json=ADMIN).status_code == 409
    assert anon_client.get("/api/setup/status").json()["needs_setup"] is False

    token = login(anon_client, ADMIN["admin_email"], ADMIN["admin_password"])
    me = anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["tenant"]["name"] == ADMIN["company_name"]

    # Falsches Passwort
    bad = anon_client.post("/api/auth/login", json={
        "email": ADMIN["admin_email"], "password": "falsch123",
    })
    assert bad.status_code == 401


def test_requests_without_token_are_rejected(anon_client):
    anon_client.post("/api/setup", json=ADMIN)
    assert anon_client.get("/api/crm/customers").status_code == 401
    assert anon_client.get("/api/ai/kpis").status_code == 401


def _create_user(client, email: str, role_name: str):
    """Legt über die DB einen Benutzer mit gegebener Rolle an (Admin-API folgt in Etappe 2)."""
    from backend.app.core.database import SessionLocal
    from backend.app.modules.auth.models import Role, User
    from backend.app.modules.auth.security import hash_password

    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        user = User(
            tenant_id=role.tenant_id, email=email, display_name=email,
            password_hash=hash_password("geheim123"), role_id=role.id,
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


def test_fine_grained_permissions(client):
    _create_user(client, "buchhaltung@testfirma.de", "Buchhaltung")
    _create_user(client, "mitarbeiter@testfirma.de", "Mitarbeiter")

    buch = {"Authorization": f"Bearer {login(client, 'buchhaltung@testfirma.de', 'geheim123')}"}
    mit = {"Authorization": f"Bearer {login(client, 'mitarbeiter@testfirma.de', 'geheim123')}"}

    # Buchhaltung: finance schreiben ja, crm nur lesen, hr gar nicht
    assert client.post("/api/finance/expenses", headers=buch, json={
        "category": "Porto", "amount_net": 10, "expense_date": "2026-06-01",
    }).status_code == 201
    assert client.get("/api/crm/customers", headers=buch).status_code == 200
    assert client.post("/api/crm/customers", headers=buch, json={"name": "X"}).status_code == 403
    assert client.get("/api/hr/employees", headers=buch).status_code == 403

    # Mitarbeiter: projects schreiben ja, finance gar nicht
    assert client.post("/api/projects", headers=mit, json={"name": "Intern"}).status_code == 201
    assert client.get("/api/finance/invoices", headers=mit).status_code == 403


def test_tenant_isolation(client):
    """Zwei Mandanten dürfen sich unter keinen Umständen sehen."""
    # Mandant A (aus Fixture) legt Daten an
    client.post("/api/crm/customers", json={"name": "Geheimkunde A", "status": "aktiv"})
    client.post("/api/knowledge/documents", json={
        "title": "SOP: Geheimprozess A", "doc_type": "sop",
        "content": "Interner Prozess von Firma A mit vertraulichen Details.",
    })

    # Mandant B registriert sich (allow_signup=true in Tests)
    second = client.post("/api/auth/register", json={
        "company_name": "Zweite Firma AG", "admin_name": "B Admin",
        "admin_email": "admin@zweite.de", "admin_password": "geheim123",
    })
    assert second.status_code == 201
    headers_b = {"Authorization": f"Bearer {second.json()['access_token']}"}

    # B sieht weder Kunden noch Wissensdokumente noch RAG-Treffer von A
    assert client.get("/api/crm/customers", headers=headers_b).json() == []
    assert client.get("/api/knowledge/documents", headers=headers_b).json() == []
    search_b = client.post("/api/ai/search", headers=headers_b,
                           json={"query": "Geheimprozess vertraulich"}).json()
    assert search_b["results"] == []
    assert client.get("/api/ai/status", headers=headers_b).json()["indexed_chunks"] == 0

    # A findet die eigenen Daten weiterhin
    search_a = client.post("/api/ai/search", json={"query": "Geheimprozess vertraulich"}).json()
    assert any("Geheimprozess" in r["title"] for r in search_a["results"])

    # KPIs sind getrennt
    assert client.get("/api/ai/kpis", headers=headers_b).json()["vertrieb"]["kunden_gesamt"] == 0
    assert client.get("/api/ai/kpis").json()["vertrieb"]["kunden_gesamt"] == 1

    # Gleiche Rechnungsnummer in beiden Mandanten erlaubt
    invoice = {"number": "RE-1", "amount_net": 100, "issue_date": "2026-06-01"}
    assert client.post("/api/finance/invoices", json=invoice).status_code == 201
    assert client.post("/api/finance/invoices", headers=headers_b, json=invoice).status_code == 201


def test_demo_seed_via_setup(anon_client):
    created = anon_client.post("/api/setup", json={**ADMIN, "with_demo_data": True})
    assert created.status_code == 201
    anon_client.headers["Authorization"] = f"Bearer {created.json()['access_token']}"

    kpis = anon_client.get("/api/ai/kpis").json()
    assert kpis["vertrieb"]["kunden_gesamt"] == 3
    assert anon_client.get("/api/ai/status").json()["indexed_chunks"] > 0
