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
