"""KI-Übersetzer: deutsche Beschreibung → validierte Builder-Artefakte.

Claude erhält den Katalog des Mandanten (Module, Felder, Events, Rollen)
und übersetzt eine Anforderung wie "Ich brauche eine Fuhrpark-Verwaltung
mit Kennzeichen und TÜV-Termin, und wenn der TÜV abläuft, soll eine
Aufgabe entstehen" in ModuleDef/AutomationDef/WidgetDef/WorkflowDef —
garantiert schema-konform über Structured Outputs.
"""

from sqlalchemy.orm import Session

from ..ai import llm
from ..modules.auth.models import Role
from .definitions import BuilderResult
from .models import CustomModule

# Stabiler Systemprompt (vor dem Cache-Breakpoint) — niemals dynamische Inhalte!
_SYSTEM_STABLE = """Du bist der Builder-Assistent eines Unternehmens-Betriebssystems (KMU-OS).
Nutzer beschreiben auf Deutsch, was sie brauchen; du übersetzt das in Bausteine:

1. MODULE (kind=module): eigene Datentabellen mit Feldern.
   Feldtypen: text, textarea, number, date, bool, select (mit options),
   reference (mit reference_target: 'crm'=Kunden, 'hr'=Mitarbeiter,
   'projects'=Projekte oder 'custom:<slug>').
2. AUTOMATIONEN (kind=automation): Wenn-Dann-Regeln.
   trigger_type 'event' (trigger_event aus dem Event-Katalog) oder
   'schedule' (schedule: 'daily@HH:MM' oder 'every:<n>m').
   Aktionen: create_record (target z. B. 'projects.task' für Aufgaben,
   'crm.interaction' für Kundennotizen, 'custom:<slug>'), update_record,
   notify (message + notify_role).
   In values/message sind Templates erlaubt: {{event.<key>}}, {{today}}.
3. WIDGETS (kind=widget): Dashboard-Kacheln (kennzahl, liste, diagramm)
   über eine source mit optionalen Bedingungen.
4. WORKFLOWS (kind=workflow): mehrstufige Genehmigungen. trigger_event
   startet eine Instanz; steps mit approver_role (existierende Rolle!).

Regeln:
- Erzeuge NUR, was der Nutzer wirklich braucht — keine ungefragten Extras.
- Nutze existierende Module/Felder/Rollen aus dem Katalog; erfinde keine.
- Slugs und Feldnamen: deutsch, snake_case, kurz.
- Wenn die Beschreibung mehrdeutig ist oder eine benötigte Rolle/ein Modul
  fehlt: stelle rueckfragen und lass artefakte leer.
- erklaerung: 2-4 Sätze auf Deutsch, was gebaut wird und wie es zusammenspielt.
- Bedingungen (conditions) sind UND-verknüpft. Für Datumsvergleiche mit heute
  nutze value '{{today}}' und op lt/gt.
"""

_STANDARD_EVENTS = [
    "crm.customer.created", "crm.customer.updated", "crm.interaction.created",
    "finance.invoice.created", "finance.invoice.updated", "finance.expense.created",
    "hr.employee.created", "hr.absence.created",
    "projects.project.created", "projects.task.created", "projects.task.updated",
    "knowledge.document.created", "knowledge.document.updated",
    "workflow.instance.completed",
]


def _tenant_catalog(db: Session) -> str:
    """Mandanten-spezifischer Kontext (hinter dem Cache-Breakpoint)."""
    lines = ["KATALOG DIESES UNTERNEHMENS:", "", "Standard-Module: crm (Kunden), finance (Rechnungen/Ausgaben), "
             "hr (Mitarbeiter/Abwesenheiten), projects (Projekte/Aufgaben), knowledge (Dokumente/SOPs)"]

    modules = db.query(CustomModule).filter(CustomModule.status == "aktiv").all()
    if modules:
        lines.append("\nVorhandene Custom-Module:")
        for module in modules:
            fields = ", ".join(f"{f.name} ({f.field_type})" for f in module.fields)
            lines.append(f"- custom:{module.slug} ({module.name_plural or module.name}): {fields}")
    else:
        lines.append("\nVorhandene Custom-Module: keine")

    events = list(_STANDARD_EVENTS)
    for module in modules:
        events.append(f"custom.{module.slug}.record.created")
        events.append(f"custom.{module.slug}.record.updated")
    lines.append("\nEvent-Katalog: " + ", ".join(events))

    roles = [r.name for r in db.query(Role).all()]
    lines.append("\nVorhandene Rollen: " + ", ".join(roles))
    return "\n".join(lines)


def translate(db: Session, description: str) -> BuilderResult | None:
    """Übersetzt die Beschreibung; None, wenn die KI nicht verfügbar ist."""
    return llm.parse(
        system_stable=_SYSTEM_STABLE,
        system_context=_tenant_catalog(db),
        user_message=f"Anforderung des Nutzers:\n{description}",
        output_format=BuilderResult,
    )
