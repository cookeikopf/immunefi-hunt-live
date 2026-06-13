"""HR-Datenmodelle: Mitarbeiter und Abwesenheiten."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.database import Base
from ...core.tenancy import TenantMixin


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Employee(TenantMixin, Base):
    __tablename__ = "hr_employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120), index=True)
    email: Mapped[str | None] = mapped_column(String(200))
    weekly_hours: Mapped[float] = mapped_column(Float, default=40.0)
    vacation_days_per_year: Mapped[int] = mapped_column(default=30)
    hired_at: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    absences: Mapped[list["Absence"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class Absence(TenantMixin, Base):
    __tablename__ = "hr_absences"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("hr_employees.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="urlaub")  # urlaub | krank | sonstiges
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    employee: Mapped[Employee] = relationship(back_populates="absences")
