"""Projekt-Datenmodelle: Projekte und Aufgaben."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.database import Base
from ...core.tenancy import TenantMixin


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Project(TenantMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("crm_customers.id"))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="aktiv")  # aktiv | pausiert | abgeschlossen
    budget: Mapped[float | None] = mapped_column(Float)
    deadline: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Task(TenantMixin, Base):
    __tablename__ = "project_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("hr_employees.id"))
    status: Mapped[str] = mapped_column(String(20), default="offen", index=True)  # offen | in_arbeit | erledigt
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped[Project] = relationship(back_populates="tasks")
