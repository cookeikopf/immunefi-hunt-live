"""Vordefinierte Rollen, die jeder neue Mandant erhält."""

from sqlalchemy.orm import Session

from .models import Role, RolePermission

BUSINESS_MODULES = ["crm", "finance", "hr", "projects", "knowledge"]

# Modul → Aktion je Rolle. "write" schließt "read" ein; "*" = alle Module.
DEFAULT_ROLES: dict[str, dict[str, str]] = {
    "Admin": {"*": "write"},
    "Geschäftsführung": {
        **{m: "write" for m in BUSINESS_MODULES},
        "ai": "write", "builder": "write", "workflows": "write",
    },
    "Buchhaltung": {
        "finance": "write", "crm": "read", "projects": "read",
        "ai": "write", "workflows": "write",
    },
    "Mitarbeiter": {
        "projects": "write", "knowledge": "write", "crm": "read", "hr": "read",
        "ai": "write", "workflows": "write",
    },
}


def seed_roles(db: Session, tenant_id: int) -> dict[str, Role]:
    """Legt die Standardrollen für einen Mandanten an (idempotent)."""
    roles: dict[str, Role] = {}
    for name, perms in DEFAULT_ROLES.items():
        role = (
            db.query(Role)
            .filter(Role.tenant_id == tenant_id, Role.name == name)
            .first()
        )
        if role is None:
            role = Role(tenant_id=tenant_id, name=name, is_system=True)
            db.add(role)
            db.flush()
            for module, action in perms.items():
                db.add(RolePermission(role_id=role.id, module=module, action=action))
        roles[name] = role
    db.flush()
    return roles
