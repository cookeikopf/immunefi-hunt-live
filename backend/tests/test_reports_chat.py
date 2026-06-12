"""Tests: Wochenbericht mit Deltas und persistenter Chat-Verlauf."""


def test_weekly_report_with_deltas(client):
    client.post("/api/finance/invoices", json={
        "number": "RE-W1", "amount_net": 1000, "issue_date": "2026-06-01",
    })

    first = client.post("/api/ai/weekly-report").json()
    assert first["deltas"] == []  # erste Erhebung
    assert first["kpis"]["finanzen"]["umsatz_gesamt_netto"] == 1000
    assert "report" in first

    # Umsatz wächst → Delta beim zweiten Bericht
    client.post("/api/finance/invoices", json={
        "number": "RE-W2", "amount_net": 500, "issue_date": "2026-06-02",
    })
    second = client.post("/api/ai/weekly-report").json()
    umsatz_delta = next(d for d in second["deltas"] if d["label"] == "Umsatz (netto)")
    assert umsatz_delta == {"label": "Umsatz (netto)", "vorher": 1000.0,
                            "jetzt": 1500.0, "delta": 500.0}


def test_chat_persists_conversation_and_history(client, monkeypatch):
    captured = {}

    def fake_complete(system, user_message, max_tokens=None, history=None):
        captured["history_length"] = len(history or [])
        return f"Antwort auf: {user_message.rsplit('Frage: ', 1)[-1]}"

    monkeypatch.setattr("backend.app.ai.assistant.llm.complete", fake_complete)

    first = client.post("/api/ai/chat", json={"question": "Wie viele Kunden haben wir?"}).json()
    conversation_id = first["conversation_id"]
    assert conversation_id is not None
    assert captured["history_length"] == 0

    second = client.post("/api/ai/chat", json={
        "question": "Und wie viele davon sind aktiv?",
        "conversation_id": conversation_id,
    }).json()
    assert second["conversation_id"] == conversation_id
    assert captured["history_length"] == 2  # Frage + Antwort der ersten Runde

    # Verlauf ist abrufbar
    conversations = client.get("/api/ai/conversations").json()
    assert len(conversations) == 1
    detail = client.get(f"/api/ai/conversations/{conversation_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]

    # Fremde Unterhaltungen sind nicht erreichbar
    from backend.tests.conftest import login
    from backend.tests.test_auth_tenancy import _create_user

    _create_user(client, "andere@testfirma.de", "Mitarbeiter")
    headers = {"Authorization": f"Bearer {login(client, 'andere@testfirma.de', 'geheim123')}"}
    assert client.get(f"/api/ai/conversations/{conversation_id}", headers=headers).status_code == 404
    assert client.post("/api/ai/chat", headers=headers, json={
        "question": "X", "conversation_id": conversation_id,
    }).status_code == 404
