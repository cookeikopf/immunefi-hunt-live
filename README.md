# KMU-OS — das Operating System für kleine und mittlere Unternehmen

**Ein System statt zehn Insellösungen:** CRM, Finanzen, Personal, Projekte und
Wissensmanagement in einer Oberfläche — mit allen Daten an einem Ort. Genau
diese Bündelung macht den Unterschied: Eine KI sieht das *gesamte* Unternehmen,
beantwortet Fragen zu Prozessen und Zahlen, erkennt Risiken und schlägt
konkrete Verbesserungen vor. Und mit dem **Builder** passt jede Firma das
System in normalem Deutsch an sich selbst an — ohne Programmierung.

## Was KMU-OS kann

| Bereich | Funktionen |
|---|---|
| **Geschäftsmodule** | Kunden & Kontakthistorie, Rechnungen (USt., Fälligkeit) & Ausgaben, Mitarbeitende & Abwesenheiten, Projekte & Aufgaben, SOPs/Regeln/Dokumente (versioniert) |
| **Firmen-Assistent** | RAG-Chat über das gesamte Unternehmen: Prozesse, Regeln, Kunden, Projekte, Zahlen — mit Quellenangaben und fortsetzbaren Unterhaltungen |
| **KI-Insights** | Regelbasierte Befunde (überfällige Rechnungen, Liquidität, überfällige Aufgaben …) + priorisierte Verbesserungsvorschläge von Claude |
| **Wochenbericht** | Lage, Entwicklung (Deltas zur Vorwoche) und Prioritäten — auf Knopfdruck oder automatisiert |
| **Builder** | Eigene Module ("Fuhrpark mit Kennzeichen und TÜV-Termin"), Wenn-Dann-Automationen, Dashboard-Widgets und mehrstufige Genehmigungs-Workflows — **per Beschreibung in normalem Deutsch**, mit Vorschau & Bestätigung; ohne KI-Schlüssel über den Form-Editor |
| **Team & Rechte** | Benutzerverwaltung, Rollen mit Rechten pro Modul (lesen/schreiben), inkl. eigener Module |
| **Einrichtung** | Setup-Wizard in einer Minute, CSV-Import für Bestandsdaten, optionale Demo-Firma |
| **Betrieb** | Self-Hosted (Docker, eine Firma) und SaaS (mandantenfähig, Registrierung zuschaltbar) aus einer Codebasis |

## In 5 Minuten startklar (Docker)

```bash
cp .env.example .env
# KMUOS_SECRET_KEY setzen (z. B. python -c "import secrets; print(secrets.token_urlsafe(48))")
# optional: ANTHROPIC_API_KEY für die KI-Funktionen

docker compose up -d
```

→ **http://localhost:8000** öffnen, Setup-Wizard ausfüllen, fertig.
Mit „Demo-Daten" startet eine komplette Musterfirma inkl. Builder-Beispielen
(Fuhrpark-Modul, TÜV-Automation, Widgets, Urlaubsfreigabe-Workflow).

Mit PostgreSQL statt SQLite: `docker compose --profile postgres up -d`
(Verbindungs-URL in `.env`, siehe Kommentare).

> **Wichtig:** Genau **1 Worker** betreiben (Standard im Container) —
> Event-Bus und Automations-Scheduler laufen in-process.

### Lokale Entwicklung

```bash
pip install -r requirements.txt
alembic upgrade head
python -m backend.seed_demo          # Demo-Firma: admin@demo.de / demo1234
uvicorn backend.app.main:app --reload
python -m pytest backend/tests       # 41 Tests
```

## Der Builder — das OS personalisiert sich selbst

Im Builder beschreibt der Nutzer auf Deutsch, was er braucht:

> *„Ich möchte unseren Fuhrpark verwalten — Kennzeichen, Marke, TÜV-Termin und
> Status. Wenn ein TÜV-Termin überschritten ist, soll automatisch eine Aufgabe
> entstehen. Und ich will eine Dashboard-Kachel mit den Fahrzeugen in der
> Werkstatt."*

Claude übersetzt das (Structured Outputs, garantiert schema-konform) in:

1. ein **Modul** mit Feldern (Text, Zahl, Datum, Auswahl, Verweis auf Kunden/Mitarbeiter/Projekte),
2. eine **Automation** (Event- oder zeitgesteuert, Bedingungen, Aktionen: Aufgabe/Notiz/Custom-Eintrag anlegen, Datensatz ändern, Rolle benachrichtigen),
3. ein **Widget** (Kennzahl, Liste, Diagramm),
4. bei Bedarf einen **Workflow** (mehrstufige Genehmigung mit Rollen je Stufe).

Der Nutzer sieht eine **editierbare Vorschau** und aktiviert erst dann.
Alles ist metadaten-getrieben — kein generierter Code. Neue Module erscheinen
sofort in Navigation, Rechte-Matrix, RAG-Index, KPIs und als Widget-Quelle.

## Architektur in Kürze

```
Module (CRM, Finanzen, HR, Projekte, Wissen, Custom) ─┐
                                                      ├─► eine Datenbank + Event-Bus
Builder (Module, Automationen, Widgets, Workflows) ───┘          │
                          ┌──────────────┬───────────────────────┤
                          ▼              ▼                       ▼
                     KPI-Engine     RAG-Index        Automationen & Workflows
                          │              │
                          ▼              ▼
                   Insights/Bericht   Firmen-Assistent (Claude)
```

- **Mandantenfähig:** tenant_id auf allen Tabellen, zentral durchgesetzt über
  SQLAlchemy-Session-Events — keine Query muss manuell filtern.
- **Feingranulare Rechte:** Rollen × Module × lesen/schreiben, inkl. `custom:<slug>`.
- **KI mit Substanz:** Hybrid-Retrieval (Vektor + BM25), Event-getriebene
  Indexierung, Prompt-Caching, adaptives Denken, Multi-Turn-Verlauf.
- **Graceful Degradation:** ohne `ANTHROPIC_API_KEY` laufen alle Module,
  Suche, Automationen, Workflows und Widgets vollständig weiter.

Details, Entscheidungen und Stolperfallen: [`docs/architecture.md`](docs/architecture.md)

## API

Vollständige OpenAPI-Dokumentation unter **/docs** (nach Login `Authorize`
mit dem Token aus `/api/auth/login`). Wichtigste Gruppen: `/api/auth`,
`/api/admin`, `/api/{crm,finance,hr,projects,knowledge}`, `/api/builder`,
`/api/custom/<slug>/records`, `/api/workflows`, `/api/ai`, `/api/imports`.

## Datenschutz (DSGVO)

Alle Geschäftsdaten bleiben in der eigenen Datenbank. An die Claude API gehen
nur die für die jeweilige Anfrage nötigen Kontextauszüge. Für den
Produktivbetrieb: AVV mit dem KI-Anbieter abschließen, Datenschutzerklärung
ergänzen, personenbezogene Daten in SOPs sparsam halten.
