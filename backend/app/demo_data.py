"""Demo-Daten einer Musterfirma.

``seed_demo_data(db)`` erwartet eine mandanten-gebundene Session
(``db.info["tenant_id"]`` gesetzt) und wird vom Setup-Wizard
("mit Demo-Daten starten") sowie vom CLI-Seed genutzt.
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from .modules.crm.models import Customer, Interaction
from .modules.finance.models import Expense, Invoice
from .modules.hr.models import Employee
from .modules.knowledge.models import KnowledgeDocument
from .modules.projects.models import Project, Task

SOPS = [
    (
        "SOP: Kunden-Onboarding",
        "sop",
        "Vertrieb",
        "Ziel: Neue Kunden strukturiert und innerhalb von 5 Arbeitstagen aufnehmen.\n\n"
        "1. Auftragsbestätigung versenden (Vorlage AB-01) — Verantwortlich: Vertrieb.\n"
        "2. Kundenakte im KMU-OS anlegen: Stammdaten, Ansprechpartner, Branche.\n"
        "3. Kickoff-Termin innerhalb von 5 Arbeitstagen vereinbaren.\n"
        "4. Projektleiter zuweisen und Projekt im System anlegen.\n"
        "5. Willkommenspaket per E-Mail senden (Vorlage WK-02).\n\n"
        "Eskalation: Kommt innerhalb von 5 Tagen kein Kickoff zustande, informiert "
        "der Vertrieb die Geschäftsführung.",
    ),
    (
        "SOP: Rechnungsstellung und Mahnwesen",
        "sop",
        "Finanzen",
        "Rechnungen werden innerhalb von 3 Arbeitstagen nach Leistungserbringung gestellt. "
        "Zahlungsziel: 14 Tage netto.\n\n"
        "Mahnstufen:\n"
        "1. Zahlungserinnerung: 3 Tage nach Fälligkeit, freundlicher Ton.\n"
        "2. Erste Mahnung: 14 Tage nach Fälligkeit, Mahngebühr 5 EUR.\n"
        "3. Zweite Mahnung: 28 Tage nach Fälligkeit, Ankündigung Inkasso.\n\n"
        "Alle Rechnungen sind GoBD-konform fortlaufend zu nummerieren und 10 Jahre aufzubewahren.",
    ),
    (
        "Regel: Urlaubsanträge",
        "regel",
        "Personal",
        "Urlaubsanträge sind mindestens 2 Wochen im Voraus über das System einzureichen. "
        "Die Genehmigung erfolgt durch die Teamleitung. Zwischen Weihnachten und Neujahr "
        "gilt Betriebsruhe; diese Tage werden auf den Jahresurlaub angerechnet. "
        "Resturlaub verfällt am 31. März des Folgejahres.",
    ),
    (
        "Regel: Datenschutz und IT-Sicherheit",
        "regel",
        "IT",
        "Kundendaten dürfen ausschließlich in den Firmensystemen verarbeitet werden (DSGVO). "
        "Private Cloud-Speicher sind untersagt. Passwörter: mindestens 12 Zeichen, "
        "Passwortmanager verpflichtend, Zwei-Faktor-Authentifizierung für alle externen Dienste. "
        "Verdacht auf Datenpannen sofort an die IT-Leitung melden (Frist: 72 Stunden, Art. 33 DSGVO).",
    ),
    (
        "Handbuch: Angebotskalkulation",
        "dokument",
        "Vertrieb",
        "Stundensätze: Beratung 120 EUR, Entwicklung 95 EUR, Support 75 EUR (jeweils netto). "
        "Auf Projekte über 20.000 EUR kann ein Rahmenrabatt von maximal 8 % gewährt werden — "
        "Freigabe durch die Geschäftsführung erforderlich. Angebote sind 30 Tage gültig "
        "und werden im KMU-OS unter dem jeweiligen Kunden dokumentiert.",
    ),
]


def seed_demo_data(db: Session) -> dict[str, int]:
    """Legt Demo-Daten für den aktuellen Mandanten an und baut den RAG-Index."""
    if db.info.get("tenant_id") is None:
        raise RuntimeError("seed_demo_data benötigt eine mandanten-gebundene Session")
    if db.query(Customer).count() > 0:
        return {}

    today = date.today()

    mueller = Customer(
        name="Müller Maschinenbau GmbH", industry="Maschinenbau", status="aktiv",
        email="info@mueller-mb.de", phone="+49 711 123456",
        notes="Stammkunde seit 2022, Rahmenvertrag Wartung.",
    )
    schmidt = Customer(
        name="Schmidt Logistik KG", industry="Logistik", status="aktiv",
        email="kontakt@schmidt-logistik.de",
    )
    weber = Customer(
        name="Weber & Söhne", industry="Handwerk", status="lead",
        notes="Empfehlung von Müller Maschinenbau. Interesse an Digitalisierung "
              "der Auftragsabwicklung.",
    )
    db.add_all([mueller, schmidt, weber])
    db.flush()

    db.add_all([
        Interaction(customer_id=mueller.id, kind="termin",
                    summary="Quartalsgespräch: Erweiterung des Wartungsvertrags um Standort Leipzig besprochen."),
        Interaction(customer_id=weber.id, kind="anruf",
                    summary="Erstgespräch geführt, Angebot für Prozessanalyse bis Ende des Monats zugesagt."),
    ])

    anna = Employee(first_name="Anna", last_name="Becker", role="Projektleiterin",
                    department="Projekte", email="a.becker@firma.de", hired_at=date(2021, 3, 1))
    jonas = Employee(first_name="Jonas", last_name="Vogel", role="Entwickler",
                     department="Entwicklung", email="j.vogel@firma.de", hired_at=date(2023, 9, 1))
    db.add_all([anna, jonas])
    db.flush()

    portal = Project(
        name="Kundenportal Müller", customer_id=mueller.id, status="aktiv",
        budget=48000, deadline=today + timedelta(days=60),
        description="Entwicklung eines Self-Service-Portals für Ersatzteilbestellungen.",
    )
    db.add(portal)
    db.flush()
    db.add_all([
        Task(project_id=portal.id, title="Anforderungsworkshop dokumentieren",
             assignee_id=anna.id, status="erledigt"),
        Task(project_id=portal.id, title="API für Ersatzteilkatalog umsetzen",
             assignee_id=jonas.id, status="in_arbeit", due_date=today + timedelta(days=14)),
        Task(project_id=portal.id, title="Lasttest vorbereiten",
             status="offen", due_date=today - timedelta(days=2)),
    ])

    db.add_all([
        Invoice(number="RE-2026-041", customer_id=mueller.id, amount_net=12500,
                issue_date=today - timedelta(days=40), due_date=today - timedelta(days=26),
                status="bezahlt", description="Meilenstein 1 Kundenportal"),
        Invoice(number="RE-2026-042", customer_id=mueller.id, amount_net=9800,
                issue_date=today - timedelta(days=20), due_date=today - timedelta(days=6),
                status="offen", description="Meilenstein 2 Kundenportal"),
        Invoice(number="RE-2026-043", customer_id=schmidt.id, amount_net=4200,
                issue_date=today - timedelta(days=10), due_date=today + timedelta(days=4),
                status="offen", description="Beratung Lagerprozesse"),
    ])
    db.add_all([
        Expense(category="Personal", amount_net=14200, expense_date=today - timedelta(days=15),
                description="Gehälter Vormonat"),
        Expense(category="Miete", amount_net=2300, expense_date=today - timedelta(days=15)),
        Expense(category="Software", amount_net=480, expense_date=today - timedelta(days=8),
                description="Lizenzen Entwicklungswerkzeuge"),
    ])

    for title, doc_type, category, content in SOPS:
        db.add(KnowledgeDocument(title=title, doc_type=doc_type, category=category, content=content))

    db.commit()

    from .ai.rag.indexer import reindex_all

    return reindex_all(db)
