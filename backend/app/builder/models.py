"""Builder-Datenmodelle: Custom-Module, Felder, Datensätze, Entwürfe.

Der Builder erzeugt KEINEN Code — Custom-Module sind Metadaten
(Modul- und Felddefinitionen), die eine generische CRUD-Engine,
dynamische UI-Formulare und der RAG-Indexer interpretieren.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base
from ..core.tenancy import TenantMixin

JsonColumn = JSON().with_variant(JSONB, "postgresql")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CustomModule(TenantMixin, Base):
    __tablename__ = "custom_modules"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(120))
    name_plural: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="aktiv")  # aktiv | archiviert
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    fields: Mapped[list["CustomField"]] = relationship(
        back_populates="module", cascade="all, delete-orphan",
        order_by="CustomField.position",
    )


class CustomField(Base):
    """Felddefinition — Zugriff ausschließlich über das (mandanten-gebundene) Modul."""

    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("custom_modules.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))      # snake_case-Schlüssel in values
    label: Mapped[str] = mapped_column(String(120))
    field_type: Mapped[str] = mapped_column(String(20))  # text|textarea|number|date|bool|select|reference
    required: Mapped[bool] = mapped_column(default=False)
    options: Mapped[list | None] = mapped_column(JsonColumn)   # select-Optionen
    reference_target: Mapped[str | None] = mapped_column(String(80))  # z. B. "crm" | "custom:fuhrpark"
    show_in_list: Mapped[bool] = mapped_column(default=True)
    position: Mapped[int] = mapped_column(default=0)

    module: Mapped[CustomModule] = relationship(back_populates="fields")


class CustomRecord(TenantMixin, Base):
    __tablename__ = "custom_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("custom_modules.id"), index=True)
    values: Mapped[dict] = mapped_column(JsonColumn, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Automation(TenantMixin, Base):
    """Wenn-Dann-Regel: Event- oder zeitgesteuert, Aktionen als JSON."""

    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    trigger_type: Mapped[str] = mapped_column(String(20))   # event | schedule
    trigger_event: Mapped[str | None] = mapped_column(String(120), index=True)
    schedule: Mapped[str | None] = mapped_column(String(40))  # daily@HH:MM | every:<n>m
    source: Mapped[str | None] = mapped_column(String(80))    # Datenquelle für schedule-Prüfungen
    conditions: Mapped[list] = mapped_column(JsonColumn, default=list)
    actions: Mapped[list] = mapped_column(JsonColumn, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AutomationRun(TenantMixin, Base):
    """Audit-Protokoll: jede Ausführung einer Automation."""

    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(ForeignKey("automations.id"), index=True)
    trigger_info: Mapped[str | None] = mapped_column(String(300))
    target_ref: Mapped[str | None] = mapped_column(String(120), index=True)  # Dedup für schedule-Treffer
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok | fehler
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Notification(TenantMixin, Base):
    """Interne Mitteilung an einen Benutzer oder eine Rolle."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("auth_users.id"), index=True)
    role_name: Mapped[str | None] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(120))  # z. B. "Automation: TÜV-Prüfung"
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Widget(TenantMixin, Base):
    """Dashboard-Kachel: Kennzahl, Liste oder Diagramm über eine Datenquelle."""

    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    widget_type: Mapped[str] = mapped_column(String(20))  # kennzahl | liste | diagramm
    source: Mapped[str] = mapped_column(String(80))
    metric: Mapped[str] = mapped_column(String(20), default="count")  # count | sum
    metric_field: Mapped[str | None] = mapped_column(String(60))
    group_by: Mapped[str | None] = mapped_column(String(60))
    conditions: Mapped[list] = mapped_column(JsonColumn, default=list)
    limit: Mapped[int] = mapped_column(default=10)
    position: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkflowDefinition(TenantMixin, Base):
    """Mehrstufiger Genehmigungsprozess, gestartet durch ein Event."""

    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    trigger_event: Mapped[str] = mapped_column(String(120), index=True)
    steps: Mapped[list] = mapped_column(JsonColumn)  # [{name, approver_role}]
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WorkflowInstance(TenantMixin, Base):
    """Ein laufender Genehmigungsvorgang zu einem konkreten Objekt."""

    __tablename__ = "workflow_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("workflow_definitions.id"), index=True)
    subject_ref: Mapped[str] = mapped_column(String(120))   # z. B. "hr.absence:12"
    subject_summary: Mapped[str] = mapped_column(Text)
    current_step: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="offen", index=True)  # offen | genehmigt | abgelehnt
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    definition: Mapped[WorkflowDefinition] = relationship()
    approvals: Mapped[list["WorkflowApproval"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )


class WorkflowApproval(TenantMixin, Base):
    __tablename__ = "workflow_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("workflow_instances.id"), index=True)
    step_index: Mapped[int] = mapped_column()
    decision: Mapped[str] = mapped_column(String(20))  # genehmigt | abgelehnt
    decided_by: Mapped[int] = mapped_column(ForeignKey("auth_users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    instance: Mapped[WorkflowInstance] = relationship(back_populates="approvals")


class BuilderDraft(TenantMixin, Base):
    """Ein Builder-Entwurf: deutsche Beschreibung → validierte Definition →
    Vorschau → Aktivierung. Trägt den Bestätigen-Flow (Etappe 4)."""

    __tablename__ = "builder_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # module | automation | widget | workflow
    description_input: Mapped[str] = mapped_column(Text)
    definition: Mapped[dict] = mapped_column(JsonColumn)
    erklaerung: Mapped[str | None] = mapped_column(Text)
    rueckfragen: Mapped[list | None] = mapped_column(JsonColumn)
    status: Mapped[str] = mapped_column(String(20), default="vorschau")  # vorschau | aktiviert | verworfen
    created_by: Mapped[int | None] = mapped_column(ForeignKey("auth_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
