"""Tests der KI-Schicht: Datenhub, RAG-Pipeline, Insights, Chat-Fallback."""

from backend.app.ai.rag.chunking import chunk_text
from backend.app.ai.rag.embeddings import HashingEmbedder, cosine


def test_chunking_respects_size_and_keeps_content():
    text = "Erster Satz über Rechnungen. " * 60
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 260 for c in chunks)  # Größe + Überlappungs-Toleranz
    assert "Rechnungen" in chunks[0]


def test_chunking_short_text_single_chunk():
    assert chunk_text("Kurzer Text.") == ["Kurzer Text."]
    assert chunk_text("   ") == []


def test_embeddings_are_deterministic_and_semantic():
    embedder = HashingEmbedder(dim=256)
    a = embedder.embed("Urlaubsantrag zwei Wochen im Voraus einreichen")
    b = embedder.embed("Urlaubsantrag zwei Wochen im Voraus einreichen")
    c = embedder.embed("Stundensatz für Entwicklung beträgt 95 Euro")
    assert a == b
    assert cosine(a, b) > 0.99
    assert cosine(a, c) < cosine(a, b)


def _create_sample_docs(client):
    client.post("/api/knowledge/documents", json={
        "title": "SOP: Urlaubsanträge", "doc_type": "sop",
        "content": "Urlaubsanträge sind mindestens 2 Wochen im Voraus über das System "
                   "einzureichen. Genehmigung durch die Teamleitung.",
    })
    client.post("/api/knowledge/documents", json={
        "title": "Handbuch: Angebotskalkulation", "doc_type": "dokument",
        "content": "Stundensätze: Beratung 120 EUR, Entwicklung 95 EUR, Support 75 EUR netto.",
    })


def test_rag_index_updates_via_events_and_search_finds_relevant_doc(client):
    _create_sample_docs(client)

    status = client.get("/api/ai/status").json()
    assert status["indexed_chunks"] >= 2  # Event-Handler haben automatisch indexiert

    search = client.post("/api/ai/search", json={"query": "Wie reiche ich Urlaub ein?"}).json()
    assert search["results"], "Suche muss Treffer liefern"
    assert search["results"][0]["title"] == "SOP: Urlaubsanträge"

    search2 = client.post("/api/ai/search", json={"query": "Stundensatz Entwicklung"}).json()
    assert search2["results"][0]["title"] == "Handbuch: Angebotskalkulation"


def test_reindex_all(client):
    _create_sample_docs(client)
    client.post("/api/crm/customers", json={"name": "Beispiel GmbH", "status": "aktiv"})

    result = client.post("/api/ai/reindex").json()
    assert result["reindexed"]["knowledge"] >= 2
    assert result["reindexed"]["crm"] >= 1
    assert result["total_chunks"] >= 3


def test_kpis_aggregate_all_modules(client):
    client.post("/api/finance/invoices", json={
        "number": "RE-100", "amount_net": 1000, "issue_date": "2026-01-01",
        "due_date": "2026-01-15", "status": "offen",
    })
    client.post("/api/finance/expenses", json={
        "category": "Miete", "amount_net": 400, "expense_date": "2026-01-05",
    })
    kpis = client.get("/api/ai/kpis").json()
    assert kpis["finanzen"]["umsatz_gesamt_netto"] == 1000
    assert kpis["finanzen"]["ergebnis_netto"] == 600
    assert kpis["finanzen"]["ueberfaellige_rechnungen"] == 1  # Fälligkeit liegt in der Vergangenheit


def test_insights_rule_engine_flags_overdue_invoice(client):
    client.post("/api/finance/invoices", json={
        "number": "RE-200", "amount_net": 5000, "issue_date": "2026-01-01",
        "due_date": "2026-01-15", "status": "offen",
    })
    insights = client.get("/api/ai/insights").json()
    areas = {f["area"] for f in insights["findings"]}
    assert "Finanzen" in areas
    assert "ai_suggestions" in insights


def test_chat_without_api_key_returns_graceful_message_and_sources(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _create_sample_docs(client)

    response = client.post("/api/ai/chat", json={"question": "Wie reiche ich Urlaub ein?"})
    assert response.status_code == 200
    data = response.json()
    assert data["ai_available"] is False
    assert "ANTHROPIC_API_KEY" in data["answer"]
    # RAG-Retrieval funktioniert unabhängig vom LLM
    assert any(s["title"] == "SOP: Urlaubsanträge" for s in data["sources"])
