"""Auth-Datenmodelle: Benutzer, Rollen, Berechtigungen.

Berechtigungsmodell: Eine Rolle hat pro Modul eine Aktion ("read" oder
"write"; write schließt read ein). ``module = "*"`` gewährt alles.
Custom-Module aus dem Builder verwenden den Modulnamen ``custom:<slug>``.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...core.database import Base
from ...core.tenancy import TenantMixin


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Role(TenantMixin, Base):
    __tablename__ = "auth_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    is_system: Mapped[bool] = mapped_column(default=False)  # vordefinierte Rollen
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    """Eine Berechtigung (Modul + Aktion) einer Rolle.

    Bewusst ohne TenantMixin: Zugriff erfolgt ausschließlich über die
    (mandanten-gebundene) Rolle.
    """

    __tablename__ = "auth_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "module"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("auth_roles.id"), index=True)
    module: Mapped[str] = mapped_column(String(80))   # crm | finance | … | "*" | custom:<slug>
    action: Mapped[str] = mapped_column(String(10))   # read | write

    role: Mapped[Role] = relationship(back_populates="permissions")


class User(TenantMixin, Base):
    __tablename__ = "auth_users"
    __table_args__ = (UniqueConstraint("tenant_id", "email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role_id: Mapped[int] = mapped_column(ForeignKey("auth_roles.id"))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    role: Mapped[Role] = relationship()
