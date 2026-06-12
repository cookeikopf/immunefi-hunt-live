"""Tests für Admin-API (Benutzer/Rollen) und CSV-Import."""

import io

from backend.tests.conftest import login


def test_admin_user_lifecycle(client):
    roles = {r["name"]: r for r in client.get("/api/admin/roles").json()}
    assert set(roles) >= {"Admin", "Geschäftsführung", "Buchhaltung", "Mitarbeiter"}

    created = client.post("/api/admin/users", json={
        "email": "neu@testfirma.de", "display_name": "Neue Kollegin",
        "password": "geheim123", "role_id": roles["Mitarbeiter"]["id"],
    })
    assert created.status_code == 201

    # Login funktioniert, Rechte greifen
    token = login(client, "neu@testfirma.de", "geheim123")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.get("/api/projects", headers=headers).status_code == 200

    # Deaktivieren sperrt den Zugang
    user_id = created.json()["id"]
    client.patch(f"/api/admin/users/{user_id}", json={"active": False})
    assert client.get("/api/projects", headers=headers).status_code == 401


def test_admin_custom_role(client):
    role = client.post("/api/admin/roles", json={
        "name": "Vertrieb",
        "permissions": [{"module": "crm", "action": "write"},
                        {"module": "ai", "action": "write"}],
    })
    assert role.status_code == 201

    client.post("/api/admin/users", json={
        "email": "vertrieb@testfirma.de", "display_name": "Vertrieb",
        "password": "geheim123", "role_id": role.json()["id"],
    })
    headers = {"Authorization": f"Bearer {login(client, 'vertrieb@testfirma.de', 'geheim123')}"}
    assert client.post("/api/crm/customers", headers=headers,
                       json={"name": "Vertriebskunde"}).status_code == 201
    assert client.get("/api/finance/invoices", headers=headers).status_code == 403

    # Admin-Rolle ist schreibgeschützt
    admin_role = next(r for r in client.get("/api/admin/roles").json() if r["name"] == "Admin")
    assert client.patch(f"/api/admin/roles/{admin_role['id']}",
                        json={"name": "Umbenannt"}).status_code == 403


def _upload(client, url: str, content: str, name: str = "daten.csv"):
    return client.post(url, files={"file": (name, io.BytesIO(content.encode("utf-8")), "text/csv")})


def test_csv_import_customers(client):
    csv_data = (
        "name;industry;email;status\n"
        "Alpha GmbH;Bau;info@alpha.de;aktiv\n"
        ";Handel;;lead\n"            # Fehler: name fehlt
        "Beta KG;Logistik;;lead\n"
    )
    report = _upload(client, "/api/imports/customers", csv_data).json()
    assert report["total"] == 3
    assert report["imported"] == 2
    assert len(report["errors"]) == 1 and report["errors"][0]["row"] == 3

    names = {c["name"] for c in client.get("/api/crm/customers").json()}
    assert {"Alpha GmbH", "Beta KG"} <= names

    # Importierte Kunden landen im RAG-Index
    search = client.post("/api/ai/search", json={"query": "Alpha GmbH Bau"}).json()
    assert any("Alpha" in r["title"] for r in search["results"])


def test_csv_import_invoices_creates_unknown_customer(client):
    csv_data = (
        "number,amount_net,issue_date,due_date,customer_name,status\n"
        "RE-900,1500.50,2026-05-01,2026-05-15,Gamma AG,offen\n"
        "RE-901,abc,2026-05-02,,,offen\n"   # Fehler: Betrag ungültig
    )
    report = _upload(client, "/api/imports/invoices", csv_data).json()
    assert report["imported"] == 1
    assert len(report["errors"]) == 1

    invoices = client.get("/api/finance/invoices").json()
    assert any(i["number"] == "RE-900" for i in invoices)
    assert any(c["name"] == "Gamma AG" for c in client.get("/api/crm/customers").json())

    jobs = client.get("/api/imports/jobs").json()
    assert jobs and jobs[0]["kind"] == "invoices"
