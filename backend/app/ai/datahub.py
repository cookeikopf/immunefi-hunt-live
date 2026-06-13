"""Datenhub: bündelt die Daten aller Module zu einer Gesamtsicht.

Das ist der zentrale Baustein des KMU-OS: Weil alle Module dieselbe
Datenbank teilen, kann hier ein konsistenter Unternehmens-Schnappschuss
(Kennzahlen + Textzusammenfassung) erzeugt werden, den sowohl das
Dashboard als auch die KI (Insights & RAG) nutzen.
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..modules.crm.models import Customer, Interaction
from ..modules.finance.models import Expense, Invoice
from ..modules.hr.models import Absence, Employee
from ..modules.knowledge.models import KnowledgeDocument
from ..modules.projects.models import Project, Task


def collect_kpis(db: Session) -> dict:
    """Berechnet die wichtigsten Kennzahlen über alle Module hinweg."""
    today = date.today()

    revenue_total = (
        db.query(func.coalesce(func.sum(Invoice.amount_net), 0.0))
        .filter(Invoice.status != "storniert")
        .scalar()
    )
    revenue_paid = (
        db.query(func.coalesce(func.sum(Invoice.amount_net), 0.0))
        .filter(Invoice.status == "bezahlt")
        .scalar()
    )
    open_invoices = db.query(Invoice).filter(Invoice.status == "offen").all()
    overdue = [
        inv for inv in open_invoices
        if inv.due_date is not None and inv.due_date < today
    ]
    expenses_total = db.query(func.coalesce(func.sum(Expense.amount_net), 0.0)).scalar()

    open_tasks = db.query(Task).filter(Task.status != "erledigt").count()
    overdue_tasks = (
        db.query(Task)
        .filter(Task.status != "erledigt", Task.due_date.isnot(None), Task.due_date < today)
        .count()
    )

    return {
        "stichtag": today.isoformat(),
        "finanzen": {
            "umsatz_gesamt_netto": round(revenue_total, 2),
            "umsatz_bezahlt_netto": round(revenue_paid, 2),
            "offene_rechnungen": len(open_invoices),
            "offener_betrag_netto": round(sum(i.amount_net for i in open_invoices), 2),
            "ueberfaellige_rechnungen": len(overdue),
            "ueberfaelliger_betrag_netto": round(sum(i.amount_net for i in overdue), 2),
            "ausgaben_gesamt_netto": round(expenses_total, 2),
            "ergebnis_netto": round(revenue_total - expenses_total, 2),
        },
        "vertrieb": {
            "kunden_gesamt": db.query(Customer).count(),
            "kunden_aktiv": db.query(Customer).filter(Customer.status == "aktiv").count(),
            "leads": db.query(Customer).filter(Customer.status == "lead").count(),
            "interaktionen": db.query(Interaction).count(),
        },
        "personal": {
            "mitarbeiter_aktiv": db.query(Employee).filter(Employee.active.is_(True)).count(),
            "abwesenheiten_erfasst": db.query(Absence).count(),
        },
        "projekte": {
            "projekte_aktiv": db.query(Project).filter(Project.status == "aktiv").count(),
            "aufgaben_offen": open_tasks,
            "aufgaben_ueberfaellig": overdue_tasks,
        },
        "wissen": {
            "dokumente": db.query(KnowledgeDocument).count(),
            "sops": db.query(KnowledgeDocument).filter(KnowledgeDocument.doc_type == "sop").count(),
            "regeln": db.query(KnowledgeDocument).filter(KnowledgeDocument.doc_type == "regel").count(),
        },
        "custom": _custom_kpis(db),
    }


def _custom_kpis(db: Session) -> dict:
    """Kennzahlen der vom Builder erzeugten Custom-Module."""
    from ..builder.models import CustomModule, CustomRecord

    result = {}
    for module in db.query(CustomModule).filter(CustomModule.status == "aktiv").all():
        result[module.slug] = {
            "name": module.name_plural or module.name,
            "eintraege": db.query(CustomRecord)
            .filter(CustomRecord.module_id == module.id).count(),
        }
    return result


def company_snapshot_text(db: Session) -> str:
    """Kompakte Textzusammenfassung des Unternehmens für KI-Prompts."""
    k = collect_kpis(db)
    f, v, p, pr = k["finanzen"], k["vertrieb"], k["personal"], k["projekte"]
    lines = [
        f"Unternehmens-Schnappschuss (Stand {k['stichtag']}):",
        f"- Umsatz gesamt (netto): {f['umsatz_gesamt_netto']:.2f} EUR, davon bezahlt: {f['umsatz_bezahlt_netto']:.2f} EUR",
        f"- Offene Rechnungen: {f['offene_rechnungen']} ({f['offener_betrag_netto']:.2f} EUR), "
        f"davon überfällig: {f['ueberfaellige_rechnungen']} ({f['ueberfaelliger_betrag_netto']:.2f} EUR)",
        f"- Ausgaben gesamt (netto): {f['ausgaben_gesamt_netto']:.2f} EUR, Ergebnis: {f['ergebnis_netto']:.2f} EUR",
        f"- Kunden: {v['kunden_gesamt']} gesamt, {v['kunden_aktiv']} aktiv, {v['leads']} Leads",
        f"- Personal: {p['mitarbeiter_aktiv']} aktive Mitarbeitende",
        f"- Projekte: {pr['projekte_aktiv']} aktiv, {pr['aufgaben_offen']} offene Aufgaben "
        f"({pr['aufgaben_ueberfaellig']} überfällig)",
        f"- Wissensbasis: {k['wissen']['dokumente']} Dokumente "
        f"({k['wissen']['sops']} SOPs, {k['wissen']['regeln']} Regeln)",
    ]
    if k["custom"]:
        custom_parts = ", ".join(
            f"{info['name']}: {info['eintraege']} Einträge" for info in k["custom"].values()
        )
        lines.append(f"- Eigene Module: {custom_parts}")
    return "\n".join(lines)
