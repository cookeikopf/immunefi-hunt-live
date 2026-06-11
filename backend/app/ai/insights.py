"""Insights-Engine: erkennt Auffälligkeiten und erzeugt Verbesserungsvorschläge.

Zweistufig:
1. Regelbasierte Befunde aus den gebündelten Kennzahlen (funktioniert
   immer, auch ohne API-Schlüssel) — z. B. überfällige Rechnungen,
   negatives Ergebnis, überfällige Aufgaben, dünne Wissensbasis.
2. KI-Analyse: Claude erhält Kennzahlen + Befunde + Unternehmens-Schnappschuss
   und formuliert konkrete, priorisierte Verbesserungsvorschläge.
"""

import json
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from ..core.config import get_settings
from . import llm
from .datahub import collect_kpis, company_snapshot_text

settings = get_settings()


@dataclass
class Finding:
    severity: str  # info | warnung | kritisch
    area: str
    message: str


def rule_based_findings(kpis: dict) -> list[Finding]:
    findings: list[Finding] = []
    f, pr, w = kpis["finanzen"], kpis["projekte"], kpis["wissen"]

    if f["ueberfaellige_rechnungen"] > 0:
        findings.append(Finding(
            "kritisch", "Finanzen",
            f"{f['ueberfaellige_rechnungen']} überfällige Rechnung(en) über insgesamt "
            f"{f['ueberfaelliger_betrag_netto']:.2f} EUR netto — Mahnwesen prüfen.",
        ))
    if f["ergebnis_netto"] < 0:
        findings.append(Finding(
            "kritisch", "Finanzen",
            f"Negatives Ergebnis: {f['ergebnis_netto']:.2f} EUR netto. "
            "Ausgabenstruktur und Preisgestaltung überprüfen.",
        ))
    if f["offener_betrag_netto"] > 0 and f["umsatz_gesamt_netto"] > 0:
        quote = f["offener_betrag_netto"] / f["umsatz_gesamt_netto"]
        if quote > 0.3:
            findings.append(Finding(
                "warnung", "Finanzen",
                f"{quote:.0%} des Umsatzes sind noch nicht bezahlt — Liquidität im Blick behalten.",
            ))
    if pr["aufgaben_ueberfaellig"] > 0:
        findings.append(Finding(
            "warnung", "Projekte",
            f"{pr['aufgaben_ueberfaellig']} überfällige Aufgabe(n) in aktiven Projekten.",
        ))
    if w["sops"] == 0:
        findings.append(Finding(
            "info", "Wissen",
            "Es sind noch keine SOPs (Standardarbeitsanweisungen) hinterlegt. "
            "Dokumentierte Prozesse machen das Unternehmen unabhängiger von Einzelpersonen "
            "und verbessern die Antworten des KI-Assistenten erheblich.",
        ))
    leads = kpis["vertrieb"]["leads"]
    if leads > 0 and kpis["vertrieb"]["interaktionen"] == 0:
        findings.append(Finding(
            "warnung", "Vertrieb",
            f"{leads} Lead(s) ohne erfasste Interaktionen — Nachfassen dokumentieren.",
        ))
    return findings


_SYSTEM = """Du bist Unternehmensberater für das deutsche KMU "{company}".
Du erhältst die gebündelten Kennzahlen aller Unternehmensbereiche sowie automatisch
erkannte Befunde. Erstelle daraus konkrete Verbesserungsvorschläge.

Format deiner Antwort:
- 3 bis 6 Vorschläge, absteigend nach Wirkung priorisiert.
- Pro Vorschlag: kurze Überschrift, 2-3 Sätze Begründung mit Bezug auf die Zahlen,
  und ein konkreter erster Schritt.
- Deutsch, sachlich, ohne Floskeln. Beziehe dich nur auf die gelieferten Daten."""


def generate_insights(db: Session) -> dict:
    kpis = collect_kpis(db)
    findings = rule_based_findings(kpis)

    payload = {
        "kennzahlen": kpis,
        "befunde": [asdict(f) for f in findings],
    }
    ai_suggestions = llm.complete(
        _SYSTEM.format(company=settings.company_name),
        "Unternehmensdaten:\n"
        + company_snapshot_text(db)
        + "\n\nDetails (JSON):\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\nBitte erstelle die Verbesserungsvorschläge.",
    )

    return {
        "kpis": kpis,
        "findings": [asdict(f) for f in findings],
        "ai_suggestions": ai_suggestions,
        "ai_available": llm.is_available(),
    }
