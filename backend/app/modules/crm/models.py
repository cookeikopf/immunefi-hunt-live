"""CRM-Datenmodelle: Kunden und Kontakthistorie."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "crm_customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    industry: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="lead")  # lead | aktiv | inaktiv
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class Interaction(Base):
    """Kontaktpunkt mit einem Kunden (Anruf, E-Mail, Termin …)."""

    __tablename__ = "crm_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("crm_customers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="notiz")  # anruf | email | termin | notiz
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    customer: Mapped[Customer] = relationship(back_populates="interactions")
