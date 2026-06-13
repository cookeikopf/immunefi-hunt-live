"""Pydantic-Definitionen der Builder-Artefakte.

Diese Schemas sind die gemeinsame Sprache von drei Konsumenten:
1. dem manuellen Form-Editor (Frontend → direkt validiert),
2. dem KI-Übersetzer (Claude Structured Outputs → BuilderResult),
3. den Ausführungs-Engines (Records, Automationen, Widgets, Workflows).

Wichtig für Structured Outputs: keine rekursiven Schemas — Bedingungen
sind deshalb eine flache UND-Liste.
"""

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

# Slugs, die mit Kern-Modulen/Routen kollidieren würden
RESERVED_SLUGS = {
    "crm", "finance", "hr", "projects", "knowledge", "ai", "admin",
    "builder", "workflows", "auth", "setup", "imports", "custom",
    "records", "health", "static",
}

FieldType = Literal["text", "textarea", "number", "date", "bool", "select", "reference"]


class FieldDef(BaseModel):
    name: str = Field(description="Technischer Feldname in snake_case, z. B. 'kennzeichen'")
    label: str = Field(description="Anzeigename, z. B. 'Kennzeichen'")
    field_type: FieldType
    required: bool = False
    options: list[str] = Field(default_factory=list, description="Optionen, nur für field_type=select")
    reference_target: str | None = Field(
        default=None,
        description="Nur für field_type=reference: Zielmodul, z. B. 'crm' (Kunden), "
                    "'hr' (Mitarbeiter), 'projects' oder 'custom:<slug>'",
    )
    show_in_list: bool = True

    @field_validator("name")
    @classmethod
    def name_is_snake(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError(f"Feldname '{value}' muss snake_case sein (a-z, 0-9, _)")
        return value


class ModuleDef(BaseModel):
    kind: Literal["module"] = "module"
    slug: str = Field(description="Technischer Name in snake_case, z. B. 'fuhrpark'")
    name: str = Field(description="Anzeigename Singular, z. B. 'Fahrzeug'")
    name_plural: str | None = Field(default=None, description="Anzeigename Plural, z. B. 'Fuhrpark'")
    description: str | None = None
    fields: list[FieldDef] = Field(min_length=1, max_length=30)

    @field_validator("slug")
    @classmethod
    def slug_is_valid(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError(f"Slug '{value}' muss snake_case sein (a-z, 0-9, _)")
        if value in RESERVED_SLUGS:
            raise ValueError(f"Slug '{value}' ist reserviert")
        return value

    @field_validator("fields")
    @classmethod
    def field_names_unique(cls, value: list[FieldDef]) -> list[FieldDef]:
        names = [f.name for f in value]
        if len(names) != len(set(names)):
            raise ValueError("Feldnamen müssen eindeutig sein")
        return value


class ConditionDef(BaseModel):
    """Eine Bedingung; mehrere Bedingungen sind UND-verknüpft (flache Liste)."""

    field: str = Field(description="Feldname im Datensatz/Event, z. B. 'status' oder 'amount_net'")
    op: Literal["eq", "ne", "gt", "lt", "gte", "lte", "contains", "is_empty", "not_empty"]
    value: str | float | bool | None = None


class ActionDef(BaseModel):
    action_type: Literal["create_record", "update_record", "notify"]
    target: str | None = Field(
        default=None,
        description="Zielmodul der Aktion: 'projects.task' (Aufgabe), 'crm.interaction' "
                    "oder 'custom:<slug>'. Nicht nötig für notify.",
    )
    values: dict[str, str] = Field(
        default_factory=dict,
        description="Feldwerte; Templates erlaubt: {{event.<key>}}, {{record.<feld>}}, {{today}}",
    )
    message: str | None = Field(default=None, description="Nachricht für notify (Templates erlaubt)")
    notify_role: str | None = Field(default=None, description="Rolle, die benachrichtigt wird, z. B. 'Geschäftsführung'")


class AutomationDef(BaseModel):
    kind: Literal["automation"] = "automation"
    name: str
    trigger_type: Literal["event", "schedule"]
    trigger_event: str | None = Field(
        default=None,
        description="Für trigger_type=event: z. B. 'finance.invoice.created', "
                    "'projects.task.updated', 'custom.<slug>.record.created'",
    )
    schedule: str | None = Field(
        default=None,
        description="Für trigger_type=schedule: 'daily@HH:MM' oder 'every:<n>m'",
    )
    source: str | None = Field(
        default=None,
        description="Nur für trigger_type=schedule: Datenquelle, deren Einträge "
                    "geprüft werden (z. B. 'custom:fuhrpark', 'finance.invoices', "
                    "'projects.tasks'). Bedingungen werden je Eintrag ausgewertet, "
                    "Aktionen je Treffer einmalig ausgeführt.",
    )
    conditions: list[ConditionDef] = Field(default_factory=list)
    actions: list[ActionDef] = Field(min_length=1, max_length=5)


class WidgetDef(BaseModel):
    kind: Literal["widget"] = "widget"
    title: str
    widget_type: Literal["kennzahl", "liste", "diagramm"]
    source: str = Field(description="Datenquelle: 'crm', 'finance.invoices', 'projects.tasks', 'custom:<slug>' …")
    metric: Literal["count", "sum"] = "count"
    metric_field: str | None = Field(default=None, description="Feld für metric=sum, z. B. 'amount_net'")
    group_by: str | None = Field(default=None, description="Gruppierungsfeld für diagramm, z. B. 'status'")
    conditions: list[ConditionDef] = Field(default_factory=list)
    limit: int = 10


class WorkflowStepDef(BaseModel):
    name: str = Field(description="Name der Stufe, z. B. 'Freigabe Teamleitung'")
    approver_role: str = Field(description="Rolle, die diese Stufe genehmigt, z. B. 'Geschäftsführung'")


class WorkflowDef(BaseModel):
    kind: Literal["workflow"] = "workflow"
    name: str
    description: str | None = None
    trigger_event: str = Field(
        description="Event, das den Workflow startet, z. B. 'hr.absence.created' "
                    "oder 'custom.<slug>.record.created'",
    )
    steps: list[WorkflowStepDef] = Field(min_length=1, max_length=5)


BuilderArtifact = Annotated[
    Union[ModuleDef, AutomationDef, WidgetDef, WorkflowDef],
    Field(discriminator="kind"),
]


class BuilderResult(BaseModel):
    """Antwortformat des KI-Übersetzers (Structured Outputs)."""

    artefakte: list[BuilderArtifact] = Field(
        description="Die zu erstellenden Bausteine. Leer, wenn Rückfragen nötig sind."
    )
    erklaerung: str = Field(
        description="Verständliche deutsche Erklärung, was gebaut wird und warum."
    )
    rueckfragen: list[str] = Field(
        default_factory=list,
        description="Klärende Rückfragen, falls die Beschreibung mehrdeutig ist.",
    )


def parse_artifact(kind: str, definition: dict):
    """Validiert eine gespeicherte Definition gegen das passende Schema."""
    model = {"module": ModuleDef, "automation": AutomationDef,
             "widget": WidgetDef, "workflow": WorkflowDef}[kind]
    return model.model_validate(definition)
