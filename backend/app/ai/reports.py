"""Wochenbericht: KPIs + Veränderung zur Vorwoche + KI-Einordnung.

Per Endpoint abrufbar und — weil als Automation planbar
('daily@MO 08:00' kommt über schedule + notify) — auch proaktiv nutzbar.
"""

from dataclasses import asdict

from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.tenancy import current_tenant
from . import llm
from .datahub import collect_kpis, company_snapshot_text
from .insights import rule_based_findings
from .models import KpiSnapshot

settings = get_settings()

# Kennzahlen, deren Veränderung im Bericht ausgewiesen wird
_DELTA_KEYS = [
    ("finanzen", "umsatz_gesamt_netto", "Umsatz (netto)"),
    ("finanzen", "ergebnis_netto", "Ergebnis (netto)"),
    ("finanzen", "offener_betrag_netto", "Offene Forderungen"),
    ("finanzen", "ueberfaellige_rechnungen", "Überfällige Rechnungen"),
    ("vertrieb", "kunden_gesamt", "Kunden"),
    ("vertrieb", "leads", "Leads"),
    ("projekte", "aufgaben_offen", "Offene Aufgaben"),
    ("projekte", "aufgaben_ueberfaellig", "Überfällige Aufgaben"),
]

_SYSTEM = """Du schreibst den internen Wochenbericht für die Geschäftsführung
des deutschen KMU "{company}". Du erhältst aktuelle Kennzahlen, die Veränderung
zur letzten Erhebung und automatisch erkannte Befunde.

Aufbau:
1. "Lage in drei Sätzen" — das Wichtigste zuerst.
2. "Entwicklung" — die relevantesten Veränderungen einordnen (warum wichtig).
3. "Diese Woche angehen" — 3 konkrete, priorisierte Punkte mit erstem Schritt.

Deutsch, sachlich, an Entscheider gerichtet. Nur die gelieferten Daten verwenden."""


def _compute_deltas(current: dict, previous: dict | None) -> list[dict]:
    if not previous:
        return []
    deltas = []
    for area, key, label in _DELTA_KEYS:
        now_value = current.get(area, {}).get(key)
        old_value = previous.get(area, {}).get(key)
        if now_value is None or old_value is None or now_value == old_value:
            continue
        deltas.append({
            "label": label,
            "vorher": old_value,
            "jetzt": now_value,
            "delta": round(now_value - old_value, 2),
        })
    return deltas


def generate_weekly_report(db: Session) -> dict:
    kpis = collect_kpis(db)
    previous = (
        db.query(KpiSnapshot).order_by(KpiSnapshot.created_at.desc()).first()
    )
    deltas = _compute_deltas(kpis, previous.snapshot if previous else None)
    findings = [asdict(f) for f in rule_based_findings(kpis)]

    tenant = current_tenant(db)
    delta_text = "\n".join(
        f"- {d['label']}: {d['vorher']} → {d['jetzt']} ({d['delta']:+g})" for d in deltas
    ) or "(Erste Erhebung — noch kein Vergleichszeitraum.)"
    findings_text = "\n".join(f"- [{f['severity']}] {f['area']}: {f['message']}" for f in findings) \
        or "(Keine Auffälligkeiten.)"

    report_text = llm.complete(
        _SYSTEM.format(company=tenant.name if tenant else settings.company_name),
        f"{company_snapshot_text(db)}\n\nVeränderungen seit dem letzten Bericht:\n"
        f"{delta_text}\n\nBefunde:\n{findings_text}\n\nBitte erstelle den Wochenbericht.",
    )

    db.add(KpiSnapshot(snapshot=kpis))
    db.commit()

    return {
        "report": report_text,
        "kpis": kpis,
        "deltas": deltas,
        "findings": findings,
        "ai_available": llm.is_available(),
    }
