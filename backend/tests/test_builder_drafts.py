"""Tests für den KI-Builder-Flow: Beschreibung → Entwurf → Vorschau → Aktivieren.

Der Claude-Aufruf wird gemockt (kein API-Key in Tests) — getestet wird die
komplette Pipeline drumherum inkl. Validierung und Materialisierung.
"""

import pytest

from backend.app.builder.definitions import BuilderResult, FieldDef, ModuleDef


@pytest.fixture()
def mocked_translation(monkeypatch):
    """Simuliert eine erfolgreiche Claude-Übersetzung."""
    result = BuilderResult(
        artefakte=[ModuleDef(
            slug="wartungen",
            name="Wartung",
            name_plural="Wartungen",
            description="Wartungstermine für Maschinen",
            fields=[
                FieldDef(name="maschine", label="Maschine", field_type="text", required=True),
                FieldDef(name="faellig_am", label="Fällig am", field_type="date"),
                FieldDef(name="erledigt", label="Erledigt", field_type="bool"),
            ],
        )],
        erklaerung="Ich lege ein Modul 'Wartungen' mit drei Feldern an.",
        rueckfragen=[],
    )
    monkeypatch.setattr("backend.app.builder.router.llm.is_available", lambda: True)
    monkeypatch.setattr("backend.app.builder.translator.llm.parse",
                        lambda **kwargs: result)
    return result


def test_draft_requires_ai_or_returns_503(client):
    response = client.post("/api/builder/draft", json={"description": "Ich brauche X"})
    assert response.status_code == 503
    assert "manuellen Editor" in response.json()["detail"]


def test_full_draft_flow(client, mocked_translation):
    created = client.post("/api/builder/draft", json={
        "description": "Ich möchte Wartungstermine für unsere Maschinen verwalten.",
    })
    assert created.status_code == 200, created.text
    data = created.json()
    assert "Wartungen" in data["erklaerung"]
    assert len(data["drafts"]) == 1
    draft = data["drafts"][0]
    assert draft["kind"] == "module"
    assert draft["status"] == "vorschau"

    # Entwurf erscheint in der Liste
    assert any(d["id"] == draft["id"] for d in client.get("/api/builder/drafts").json())

    # Nutzer passt die Vorschau an (Feld ergänzen) — wird re-validiert
    definition = draft["definition"]
    definition["fields"].append({
        "name": "kosten", "label": "Kosten (€)", "field_type": "number",
        "required": False, "options": [], "reference_target": None, "show_in_list": True,
    })
    patched = client.patch(f"/api/builder/drafts/{draft['id']}", json={"definition": definition})
    assert patched.status_code == 200

    # Kaputte Definition wird abgelehnt
    broken = {**definition, "fields": []}
    assert client.patch(f"/api/builder/drafts/{draft['id']}",
                        json={"definition": broken}).status_code == 422

    # Aktivieren materialisiert das Modul
    activated = client.post(f"/api/builder/drafts/{draft['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["activated"]["slug"] == "wartungen"

    # Doppelt aktivieren geht nicht
    assert client.post(f"/api/builder/drafts/{draft['id']}/activate").status_code == 409

    # Das Modul ist sofort benutzbar (inkl. des nachträglich ergänzten Felds)
    record = client.post("/api/custom/wartungen/records", json={
        "maschine": "Fräse 3", "faellig_am": "2026-08-01", "kosten": 450.0,
    })
    assert record.status_code == 201

    # … und im RAG-Index auffindbar
    search = client.post("/api/ai/search", json={"query": "Wartung Fräse fällig"}).json()
    assert any("Wartung" in r["title"] for r in search["results"])


def test_discard_draft(client, mocked_translation):
    created = client.post("/api/builder/draft", json={"description": "Wartungen bitte"})
    draft_id = created.json()["drafts"][0]["id"]
    discarded = client.post(f"/api/builder/drafts/{draft_id}/discard")
    assert discarded.json()["status"] == "verworfen"
    assert client.get("/api/builder/drafts").json() == []
