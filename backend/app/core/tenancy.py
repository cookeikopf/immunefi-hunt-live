"""Mandantenfähigkeit (Multi-Tenancy).

Kernidee: Jede Tabelle mit Geschäftsdaten trägt eine ``tenant_id``
(über ``TenantMixin``). Die Durchsetzung passiert zentral über
SQLAlchemy-Session-Events statt an jeder Query-Stelle:

- ``do_orm_execute`` hängt an jeden ORM-SELECT/UPDATE/DELETE automatisch
  das Kriterium ``tenant_id == session.info["tenant_id"]`` an.
- ``before_flush`` setzt ``tenant_id`` auf neuen Objekten automatisch
  und verhindert das Anlegen ohne Mandanten-Bindung.

Sessions ohne ``info["tenant_id"]`` (z. B. Login, Setup) sind bewusst
ungescoped — sie dürfen nur in der Auth-/Bootstrap-Schicht vorkommen.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, event
from sqlalchemy.orm import (
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    with_loader_criteria,
)

from .database import Base


class Tenant(Base):
    """Ein Mandant = eine Firma. Self-Hosted-Installationen haben genau einen."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(default=True)
    # Billing-Stub für späteren SaaS-Ausbau (kein Billing in v1.0)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class TenantMixin:
    """Markiert ein Modell als mandanten-gebunden."""

    @declared_attr
    def tenant_id(cls) -> Mapped[int]:  # noqa: N805 - SQLAlchemy-declared_attr
        return mapped_column(ForeignKey("tenants.id"), index=True, nullable=False)


def current_tenant(db: Session) -> Tenant | None:
    tenant_id = db.info.get("tenant_id")
    return db.get(Tenant, tenant_id) if tenant_id is not None else None


def tenant_get(db: Session, model, object_id: int):
    """Mandantensicheres ``Session.get()``.

    ``db.get()`` kann über die Identity-Map am Loader-Kriterium vorbei
    Objekte liefern — diese Variante erzwingt einen gefilterten SELECT.
    """
    return db.query(model).filter(model.id == object_id).first()


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_criteria(execute_state) -> None:
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    if not (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        return
    tenant_id = execute_state.session.info.get("tenant_id")
    if tenant_id is None:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantMixin,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _assign_tenant_id(session: Session, flush_context, instances) -> None:
    tenant_id = session.info.get("tenant_id")
    for obj in session.new:
        if isinstance(obj, TenantMixin) and getattr(obj, "tenant_id", None) is None:
            if tenant_id is None:
                raise RuntimeError(
                    f"{type(obj).__name__} ohne tenant_id angelegt und Session "
                    "ist nicht mandanten-gebunden (db.info['tenant_id'] fehlt)."
                )
            obj.tenant_id = tenant_id
