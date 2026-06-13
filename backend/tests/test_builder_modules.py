"""Tests für Custom-Module: Anlegen, Validierung, RAG/KPI-Integration, Rechte."""

from backend.tests.conftest import login

FUHRPARK = {
    "kind": "module",
    "slug": "fuhrpark",
    "name": "Fahrzeug",
    "name_plural": "Fuhrpark",
    "description": "Firmenfahrzeuge mit TÜV-Terminen",
    "fields": [
        {"name": "kennzeichen", "label": "Kennzeichen", "field_type": "text", "required": True},
        {"name": "marke", "label": "Marke", "field_type": "text"},
        {"name": "tuev_datum", "label": "TÜV-Termin", "field_type": "date"},
        {"name": "status", "label": "Status", "field_type": "select",
         "options": ["verfügbar", "unterwegs", "werkstatt"]},
        {"name": "fahrer", "label": "Stammfahrer", "field_type": "reference",
         "reference_target": "hr"},
    ],
}


def test_module_lifecycle_and_records(client):
    created = client.post("/api/builder/modules", json=FUHRPARK)
    assert created.status_code == 201, created.text
    assert client.post("/api/builder/modules", json=FUHRPARK).status_code == 409

    # Reservierte Slugs und kaputte Feldnamen werden abgelehnt
    assert client.post("/api/builder/modules", json={**FUHRPARK, "slug": "crm"}).status_code == 422
    bad_field = {**FUHRPARK, "slug": "x_test",
                 "fields": [{"name": "Großbuchstabe", "label": "X", "field_type": "text"}]}
    assert client.post("/api/builder/modules", json=bad_field).status_code == 422

    # Record anlegen
    record = client.post("/api/custom/fuhrpark/records", json={
        "kennzeichen": "S-KM 1234", "marke": "VW Crafter",
        "tuev_datum": "2026-09-01", "status": "verfügbar",
    })
    assert record.status_code == 201, record.text
    record_id = record.json()["id"]

    # Validierung: Pflichtfeld + Select-Option + Zahlentyp
    assert client.post("/api/custom/fuhrpark/records", json={"marke": "Ford"}).status_code == 422
    assert client.post("/api/custom/fuhrpark/records", json={
        "kennzeichen": "S-XY 1", "status": "geparkt",
    }).status_code == 422

    # Update ersetzt Werte
    updated = client.patch(f"/api/custom/fuhrpark/records/{record_id}",
                           json={"status": "werkstatt"})
    assert updated.json()["values"]["status"] == "werkstatt"
    assert updated.json()["values"]["kennzeichen"] == "S-KM 1234"

    # Liste enthält Modul-Metadaten + Records
    listing = client.get("/api/custom/fuhrpark/records").json()
    assert listing["module"]["name_plural"] == "Fuhrpark"
    assert len(listing["records"]) == 1


def test_custom_records_flow_into_rag_and_kpis(client):
    client.post("/api/builder/modules", json=FUHRPARK)
    client.post("/api/custom/fuhrpark/records", json={
        "kennzeichen": "S-KM 9999", "marke": "Mercedes Sprinter",
        "tuev_datum": "2026-07-15",
    })

    search = client.post("/api/ai/search", json={"query": "Sprinter Kennzeichen TÜV"}).json()
    assert any("Fahrzeug" in r["title"] for r in search["results"])

    kpis = client.get("/api/ai/kpis").json()
    assert kpis["custom"]["fuhrpark"]["eintraege"] == 1

    # Löschung entfernt auch RAG-Chunks
    record_id = client.get("/api/custom/fuhrpark/records").json()["records"][0]["id"]
    client.delete(f"/api/custom/fuhrpark/records/{record_id}")
    search2 = client.post("/api/ai/search", json={"query": "Sprinter Kennzeichen TÜV"}).json()
    assert not any("Fahrzeug" in r["title"] for r in search2["results"])


def test_custom_module_permissions(client):
    client.post("/api/builder/modules", json=FUHRPARK)

    # Mitarbeiter bekommt Standard-Schreibrecht auf neue Custom-Module …
    from backend.tests.test_auth_tenancy import _create_user

    _create_user(client, "fahrer@testfirma.de", "Mitarbeiter")
    headers = {"Authorization": f"Bearer {login(client, 'fahrer@testfirma.de', 'geheim123')}"}
    assert client.get("/api/custom/fuhrpark/records", headers=headers).status_code == 200
    assert client.post("/api/custom/fuhrpark/records", headers=headers,
                       json={"kennzeichen": "S-AB 7"}).status_code == 201
    # … aber kein Builder-Recht (kann keine Module bauen)
    assert client.post("/api/builder/modules", headers=headers,
                       json={**FUHRPARK, "slug": "anderes"}).status_code == 403

    # Admin entzieht das Recht über die Rechte-Matrix
    roles = client.get("/api/admin/roles").json()
    mitarbeiter = next(r for r in roles if r["name"] == "Mitarbeiter")
    new_permissions = [p for p in mitarbeiter["permissions"] if p["module"] != "custom:fuhrpark"]
    client.patch(f"/api/admin/roles/{mitarbeiter['id']}", json={"permissions": new_permissions})
    assert client.get("/api/custom/fuhrpark/records", headers=headers).status_code == 403

    # Sichtbare Module für den Mitarbeiter sind jetzt leer
    visible = client.get("/api/custom/modules", headers=headers).json()
    assert visible == []
