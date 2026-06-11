"""Finanz-Datenmodelle: Rechnungen (Einnahmen) und Ausgaben."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Invoice(Base):
    __tablename__ = "finance_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("crm_customers.id"), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    amount_net: Mapped[float] = mapped_column(Float)        # Netto in EUR
    vat_rate: Mapped[float] = mapped_column(Float, default=19.0)  # USt. in %
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="offen")  # offen | bezahlt | überfällig | storniert
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def amount_gross(self) -> float:
        return round(self.amount_net * (1 + self.vat_rate / 100), 2)


class Expense(Base):
    __tablename__ = "finance_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(100), index=True)  # z. B. Miete, Personal, Material
    description: Mapped[str | None] = mapped_column(Text)
    amount_net: Mapped[float] = mapped_column(Float)
    expense_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
