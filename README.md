# KMU-OS — Operating System für kleine und mittlere Unternehmen

Ein integriertes Betriebssystem für deutsche KMUs: **CRM, Finanzen, Personal,
Projekte und Wissensmanagement** in einem System. Weil alle Daten an einem Ort
gebündelt sind, kann eine KI das Unternehmen ganzheitlich analysieren — und
über ein eingebautes **RAG-System** entsteht ein firmeneigener KI-Assistent,
der Prozeduren, Regeln und alle Geschäftsdaten des Unternehmens kennt.

## Kernidee

```
┌─────────────────────────── KMU-OS ───────────────────────────┐
│                                                              │
│  CRM        Finanzen     Personal     Projekte     Wissen    │
│  Kunden     Rechnungen   Mitarbeiter  Aufgaben     SOPs      │
│  Kontakte   Ausgaben     Abwesenheit  Deadlines    Regeln    │
│     │           │            │           │           │       │
│     └───────────┴─────┬──────┴───────────┴───────────┘       │
│                       ▼                                      │
│                  DATENHUB  (eine Datenbank, ein Event-Bus)   │
│                  ┌────┴─────┐                                │
│                  ▼          ▼                                │
│            KPI-Engine   RAG-Index (Chunks + Embeddings)      │
│                  │          │                                │
│                  ▼          ▼                                │
│            KI-Insights   Firmen-Assistent (Claude)           │
│            "Was sollten  "Wie läuft unser Onboarding?"       │
│             wir besser    "Welche Rechnungen sind            │
│             machen?"       überfällig?"                      │
└──────────────────────────────────────────────────────────────┘
```

1. **Module steuern das Tagesgeschäft** — jede Kundenanlage, Rechnung,
   Aufgabe und SOP landet in einer gemeinsamen Datenbank.
2. **Der Datenhub bündelt alles** — Kennzahlen über alle Bereiche hinweg,
   plus ein Event-Bus, der Änderungen sofort an die KI-Schicht meldet.
3. **Das RAG-System macht das Wissen abfragbar** — Dokumente, SOPs, Regeln
   und Geschäftsdaten werden automatisch in durchsuchbare Chunks zerlegt und
   eingebettet. Der Firmen-Assistent beantwortet Fragen ausschließlich auf
   Basis der echten Unternehmensdaten („firmeneigenes LLM").
4. **Die Insights-Engine schlägt Verbesserungen vor** — regelbasierte Befunde
   (überfällige Rechnungen, Liquidität, überfällige Aufgaben …) plus
   priorisierte KI-Vorschläge von Claude auf Basis der gebündelten Zahlen.

## Schnellstart

```bash
# 1. Abhängigkeiten installieren
pip install -r requirements.txt

# 2. (Optional) API-Schlüssel für die KI-Funktionen hinterlegen
cp .env.example .env        # ANTHROPIC_API_KEY eintragen

# 3. Demo-Daten einer Musterfirma einspielen (inkl. RAG-Index)
python -m backend.seed_demo

# 4. Starten
uvicorn backend.app.main:app --reload
```

Danach:

- **Dashboard:** http://localhost:8000 — Kennzahlen, Firmen-Assistent, KI-Insights
- **API-Dokumentation (OpenAPI):** http://localhost:8000/docs

> Ohne `ANTHROPIC_API_KEY` laufen alle Module, das Dashboard und die
> RAG-Suche vollständig — nur die LLM-Antworten werden durch einen
> Hinweis ersetzt.

## Module & API

| Modul | Endpunkte | Inhalt |
|---|---|---|
| CRM | `/api/crm/customers`, `…/interactions` | Kunden, Status (Lead/aktiv), Kontakthistorie |
| Finanzen | `/api/finance/invoices`, `/api/finance/expenses` | Rechnungen mit USt. & Fälligkeit, Ausgaben |
| Personal | `/api/hr/employees`, `…/absences` | Mitarbeitende, Urlaub & Krankheit |
| Projekte | `/api/projects`, `…/tasks` | Projekte mit Budget/Deadline, Aufgaben |
| Wissen | `/api/knowledge/documents` | SOPs, Regeln, Dokumente (versioniert) |
| KI | `/api/ai/chat`, `/search`, `/insights`, `/kpis`, `/reindex`, `/status` | Assistent, RAG-Suche, Vorschläge |

## Die KI-Schicht im Detail

**Datenhub** (`backend/app/ai/datahub.py`) — berechnet bereichsübergreifende
KPIs und einen Unternehmens-Schnappschuss als Text, der jedem KI-Prompt
beiliegt.

**RAG-Pipeline** (`backend/app/ai/rag/`)
- *Chunking:* Dokumente werden an Absatz-/Satzgrenzen in überlappende
  Abschnitte zerlegt.
- *Embeddings:* Standardmäßig ein deterministischer Hashing-Embedder
  (offline, ohne externe Modelle). Die Schnittstelle ist pluggable — ein
  semantisches Embedding-Modell kann später eingesteckt werden, ohne den
  Rest zu ändern.
- *Hybrid-Retrieval:* Vektor-Ähnlichkeit + BM25-Keyword-Score, damit sowohl
  semantische Nähe als auch exakte Begriffe (Rechnungsnummern, Namen) treffen.
- *Indexer:* hört auf den Event-Bus — jede Änderung an Dokumenten, Kunden,
  Projekten oder Mitarbeitenden aktualisiert den Index sofort. Voll-Reindex
  über `POST /api/ai/reindex`.

**Firmen-Assistent** (`backend/app/ai/assistant.py`) — holt zu jeder Frage die
relevantesten Chunks, baut den Kontext (Schnappschuss + Quellen) und fragt
Claude (`claude-opus-4-8`, adaptives Denken, Streaming, Prompt-Caching für
den Firmenkontext). Antworten nennen ihre Quellen.

**Insights-Engine** (`backend/app/ai/insights.py`) — regelbasierte Befunde
laufen immer; Claude formuliert daraus priorisierte, konkrete
Verbesserungsvorschläge mit erstem Schritt.

## Tests

```bash
python -m pytest backend/tests
```

14 Tests decken die Geschäftsmodule, die RAG-Pipeline (Chunking, Embeddings,
Event-getriebene Indexierung, Suche), den KPI-Datenhub, die Insights-Regeln
und den Chat-Fallback ohne API-Schlüssel ab.

## Architektur & Ausbaustufen

Details in [`docs/architecture.md`](docs/architecture.md) — u. a. wie ein
semantisches Embedding-Modell, Authentifizierung/Mandantenfähigkeit und
weitere Module (Einkauf, Lager, DATEV-Export) ergänzt werden können.
