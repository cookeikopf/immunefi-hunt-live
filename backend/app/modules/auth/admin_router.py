"""Admin-Endpunkte: Benutzer- und Rollenverwaltung (Modul "admin")."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.tenancy import tenant_get
from .deps import get_tenant_db, require_module
from .models import Role, RolePermission, User
from .security import hash_password

router = APIRouter(
    prefix="/api/admin", dependencies=[Depends(require_module("admin"))], tags=["Administration"]
)

# Bekannte Standard-Module für die Rechte-Matrix im UI.
# Custom-Module (custom:<slug>) kommen ab Etappe 3 dynamisch dazu.
KNOWN_MODULES = [
    "crm", "finance", "hr", "projects", "knowledge",
    "ai", "builder", "workflows", "admin",
]


class PermissionIn(BaseModel):
    module: str
    action: str  # read | write


class RoleCreate(BaseModel):
    name: str
    permissions: list[PermissionIn] = []


class RoleUpdate(BaseModel):
    name: str | None = None
    permissions: list[PermissionIn] | None = None


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    password: str
    role_id: int


class UserUpdate(BaseModel):
    display_name: str | None = None
    role_id: int | None = None
    active: bool | None = None
    password: str | None = None


def _role_out(role: Role) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "is_system": role.is_system,
        "permissions": [{"module": p.module, "action": p.action} for p in role.permissions],
    }


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role_id": user.role_id,
        "role": user.role.name,
        "active": user.active,
    }


@router.get("/modules")
def list_modules(db: Session = Depends(get_tenant_db)):
    modules = list(KNOWN_MODULES)
    try:  # Custom-Module einbeziehen, sobald der Builder (Etappe 3) aktiv ist
        from ...builder.models import CustomModule

        modules += [
            f"custom:{m.slug}"
            for m in db.query(CustomModule).filter(CustomModule.status == "aktiv").all()
        ]
    except ImportError:
        pass
    return {"modules": modules, "actions": ["read", "write"]}


@router.get("/roles")
def list_roles(db: Session = Depends(get_tenant_db)):
    return [_role_out(r) for r in db.query(Role).order_by(Role.name).all()]


@router.post("/roles", status_code=201)
def create_role(data: RoleCreate, db: Session = Depends(get_tenant_db)):
    if db.query(Role).filter(Role.name == data.name).first():
        raise HTTPException(409, "Rollenname existiert bereits")
    role = Role(name=data.name, is_system=False)
    db.add(role)
    db.flush()
    for perm in data.permissions:
        if perm.action not in ("read", "write"):
            raise HTTPException(422, "action muss read oder write sein")
        db.add(RolePermission(role_id=role.id, module=perm.module, action=perm.action))
    db.commit()
    return _role_out(role)


@router.patch("/roles/{role_id}")
def update_role(role_id: int, data: RoleUpdate, db: Session = Depends(get_tenant_db)):
    role = tenant_get(db, Role, role_id)
    if role is None:
        raise HTTPException(404, "Rolle nicht gefunden")
    if role.is_system and role.name == "Admin":
        raise HTTPException(403, "Die Admin-Rolle kann nicht verändert werden")
    if data.name:
        role.name = data.name
    if data.permissions is not None:
        db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
        for perm in data.permissions:
            if perm.action not in ("read", "write"):
                raise HTTPException(422, "action muss read oder write sein")
            db.add(RolePermission(role_id=role.id, module=perm.module, action=perm.action))
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.get("/users")
def list_users(db: Session = Depends(get_tenant_db)):
    return [_user_out(u) for u in db.query(User).order_by(User.email).all()]


@router.post("/users", status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_tenant_db)):
    if len(data.password) < 8:
        raise HTTPException(422, "Passwort muss mindestens 8 Zeichen haben")
    if tenant_get(db, Role, data.role_id) is None:
        raise HTTPException(404, "Rolle nicht gefunden")
    email = str(data.email).lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "E-Mail existiert bereits")
    user = User(
        email=email,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        role_id=data.role_id,
    )
    db.add(user)
    db.commit()
    return _user_out(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_tenant_db)):
    user = tenant_get(db, User, user_id)
    if user is None:
        raise HTTPException(404, "Benutzer nicht gefunden")
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.role_id is not None:
        if tenant_get(db, Role, data.role_id) is None:
            raise HTTPException(404, "Rolle nicht gefunden")
        user.role_id = data.role_id
    if data.active is not None:
        user.active = data.active
    if data.password:
        if len(data.password) < 8:
            raise HTTPException(422, "Passwort muss mindestens 8 Zeichen haben")
        user.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(user)
    return _user_out(user)
