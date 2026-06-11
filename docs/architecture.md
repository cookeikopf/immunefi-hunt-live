# KMU-OS — Architektur

## Leitprinzipien

1. **Eine Datenbank, ein Datenmodell.** Alle Module schreiben in dieselbe
   (standardmäßig SQLite-)Datenbank. Das ist die Voraussetzung dafür, dass
   KI-Analysen das *gesamte* Unternehmen sehen, statt Datensilos abfragen
   zu müssen. Für größere Installationen genügt es, `KMUOS_DATABASE_URL`
   auf PostgreSQL umzustellen.
2. **Module sind dünn, der Hub ist die Intelligenz.** Jedes Modul besteht
   aus `models.py` (SQLAlchemy), `schemas.py` (Pydantic) und `router.py`
   (FastAPI). Bereichsübergreifende Logik (KPIs, Indexierung, KI) lebt in
   `backend/app/ai/`.
3. **Events statt Kopplung.** Module publizieren Domänen-Ereignisse
   (`finance.invoice.created`, `knowledge.document.updated` …) auf einen
   In-Process-Bus. Der RAG-Indexer abonniert sie und hält den KI-Wissensstand
   automatisch aktuell — die Module wissen nichts von der KI-Schicht.
4. **KI degradiert sanft.** Ohne `ANTHROPIC_API_KEY` funktionieren alle
   Module, KPIs, Befunde und die RAG-Suche; nur die LLM-Texte entfallen.
   So bleibt das System offline entwickel- und testbar.

## Schichten

```
HTTP (FastAPI)
 ├── Modul-Router  /api/crm /api/finance /api/hr /api/projects /api/knowledge
 └── KI-Router     /api/ai/{chat,search,insights,kpis,reindex,status}
        │
 Geschäftslogik
 ├── Module (models/schemas/router je Domäne)
 └── KI-Schicht
      ├── datahub.py    KPIs + Unternehmens-Schnappschuss
      ├── insights.py   Regel-Befunde + Claude-Vorschläge
      ├── assistant.py  RAG-Chat ("firmeneigenes LLM")
      ├── llm.py        Anthropic-SDK-Wrapper (Streaming, adaptives Denken,
      │                 Prompt-Caching, Fehlerbehandlung, Offline-Fallback)
      └── rag/
           ├── chunking.py     satz-/absatzbasierte Chunks mit Überlappung
           ├── embeddings.py   Embedder-Protokoll + HashingEmbedder
           ├── vectorstore.py  RagChunk-Tabelle + Brute-Force-Cosinus
           ├── retriever.py    Hybrid: Vektor (60 %) + BM25 (40 %)
           └── indexer.py      Event-Handler + Voll-Reindex
        │
 Infrastruktur
 ├── core/database.py  SQLAlchemy-Engine/Session, init_db()
 ├── core/events.py    In-Process-Event-Bus (publish/subscribe)
 └── core/config.py    Pydantic-Settings (Präfix KMUOS_, .env)
```

## Was wird indexiert?

| Quelle | Repräsentation im Index |
|---|---|
| Wissensdokumente (SOPs, Regeln, Dokumente) | Titel + Volltext, gechunkt |
| Kunden | "Kundenkarte": Stammdaten, Status, Notizen, letzte 5 Interaktionen |
| Projekte | Name, Beschreibung, Budget, Deadline, offene Aufgaben |
| Mitarbeitende | Rolle, Abteilung, Arbeitszeitmodell |

Kennzahlen (Umsatz, offene Posten …) werden **nicht** indexiert, sondern bei
jeder Anfrage frisch aus dem Datenhub berechnet und dem Prompt als
Schnappschuss beigelegt — Zahlen sind so nie veraltet.

## Entscheidungen & Begründungen

**Warum ein Hashing-Embedder statt eines neuronalen Modells?**
Null Abhängigkeiten, deterministisch, offline lauffähig — und für
KMU-Korpora in Kombination mit BM25 erstaunlich treffsicher. Die
`Embedder`-Schnittstelle (`embed(text) -> list[float]`, Attribut `dim`)
erlaubt den späteren Tausch gegen z. B. `sentence-transformers`
(multilingual-e5) oder einen API-Dienst: nur `indexer.py` muss den anderen
Embedder instanziieren, danach `POST /api/ai/reindex` aufrufen.

**Warum Brute-Force-Suche statt Vektordatenbank?**
Bei < 50.000 Chunks ist die Cosinus-Suche über alle Zeilen in Millisekunden
erledigt. Eine Vektordatenbank (pgvector, Qdrant …) lohnt erst bei deutlich
größeren Korpora — der `VectorStore` kapselt die Suche, sodass der Tausch
lokal bleibt.

**Warum Claude mit Prompt-Caching?**
Der Systemprompt (Firmenkontext, Antwortregeln) ist über Anfragen hinweg
identisch — mit `cache_control: ephemeral` wird er nur einmal verarbeitet.
Adaptives Denken (`thinking: adaptive`) lässt das Modell selbst entscheiden,
wie viel Reasoning eine Frage braucht; Streaming + `get_final_message()`
schützt lange Antworten vor HTTP-Timeouts.

## Ausbaustufen (Roadmap-Vorschläge)

1. **Authentifizierung & Rollen** — OAuth2/OIDC, Rollen je Modul
   (z. B. Finanzen nur für Buchhaltung), Audit-Log.
2. **Semantische Embeddings** — multilinguales Embedding-Modell einstecken,
   Re-Ranking der Hybrid-Treffer durch Claude.
3. **Weitere Module** — Einkauf/Lieferanten, Lager, Zeiterfassung,
   DATEV-/GoBD-Export, E-Rechnung (XRechnung/ZUGFeRD).
4. **Konversationsgedächtnis** — Chat-Verläufe persistieren und bei langen
   Sitzungen serverseitige Kompaktierung der Claude-API nutzen.
5. **Proaktive KI** — Insights periodisch berechnen und als Wochenbericht
   per E-Mail versenden; Schwellwert-Alarme über den Event-Bus.
6. **Mandantenfähigkeit** — `tenant_id` über alle Tabellen + Row-Level-
   Security, wenn mehrere Firmen eine Installation teilen.

## Datenschutz-Hinweise (DSGVO)

- Alle Geschäftsdaten bleiben in der lokalen Datenbank; an die Claude API
  werden nur die für eine Anfrage nötigen Kontextauszüge übertragen.
- Für den Produktivbetrieb: Auftragsverarbeitungsvertrag (AVV) mit dem
  KI-Anbieter abschließen und in der Datenschutzerklärung aufführen.
- Personenbezogene Daten in SOPs/Notizen sparsam halten — sie landen im
  RAG-Index und damit potenziell im KI-Kontext.
