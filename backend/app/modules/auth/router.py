"""Auth- und Setup-Endpunkte.

- /api/setup: Ersteinrichtung (Onboarding) — nur solange kein Mandant existiert.
- /api/auth/register: Selbst-Registrierung neuer Firmen (SaaS, per Setting schaltbar).
- /api/auth/login, /api/auth/me
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ...core.config import get_settings
from ...core.database import get_db
from ...core.tenancy import Tenant
from .deps import get_current_user
from .models import Role, User
from .roles import seed_roles
from .security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["Auth & Setup"])

settings = get_settings()


# ---- Schemas ----

class SetupRequest(BaseModel):
    company_name: str
    industry: str | None = None
    admin_name: str
    admin_email: EmailStr
    admin_password: str
    with_demo_data: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_slug: str | None = None  # nötig, wenn die E-Mail in mehreren Firmen existiert


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "firma"


def _user_info(user: User, tenant: Tenant) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role.name,
        "tenant": {"id": tenant.id, "slug": tenant.slug, "name": tenant.name},
    }


def create_tenant_with_admin(
    db: Session,
    company_name: str,
    industry: str | None,
    admin_name: str,
    admin_email: str,
    admin_password: str,
) -> tuple[Tenant, User]:
    base_slug = _slugify(company_name)
    slug = base_slug
    suffix = 2
    while db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    tenant = Tenant(slug=slug, name=company_name, industry=industry)
    db.add(tenant)
    db.flush()

    roles = seed_roles(db, tenant.id)
    admin = User(
        tenant_id=tenant.id,
        email=admin_email.lower(),
        display_name=admin_name,
        password_hash=hash_password(admin_password),
        role_id=roles["Admin"].id,
    )
    db.add(admin)
    db.commit()
    return tenant, admin


# ---- Setup (Ersteinrichtung) ----

@router.get("/api/setup/status")
def setup_status(db: Session = Depends(get_db)):
    return {
        "needs_setup": db.query(Tenant).count() == 0,
        "allow_signup": settings.allow_signup,
        "app": settings.app_name,
    }


@router.post("/api/setup", response_model=TokenResponse, status_code=201)
def initial_setup(data: SetupRequest, db: Session = Depends(get_db)):
    if db.query(Tenant).count() > 0:
        raise HTTPException(409, "Setup wurde bereits durchgeführt")
    if len(data.admin_password) < 8:
        raise HTTPException(422, "Passwort muss mindestens 8 Zeichen haben")

    tenant, admin = create_tenant_with_admin(
        db, data.company_name, data.industry, data.admin_name,
        str(data.admin_email), data.admin_password,
    )

    if data.with_demo_data:
        from ...demo_data import seed_demo_data

        db.info["tenant_id"] = tenant.id
        seed_demo_data(db)
        db.info.pop("tenant_id", None)

    return TokenResponse(
        access_token=create_access_token(admin.id, tenant.id),
        user=_user_info(admin, tenant),
    )


# ---- Registrierung weiterer Firmen (SaaS) ----

@router.post("/api/auth/register", response_model=TokenResponse, status_code=201)
def register(data: SetupRequest, db: Session = Depends(get_db)):
    if not settings.allow_signup:
        raise HTTPException(403, "Registrierung ist auf dieser Installation deaktiviert")
    if len(data.admin_password) < 8:
        raise HTTPException(422, "Passwort muss mindestens 8 Zeichen haben")
    tenant, admin = create_tenant_with_admin(
        db, data.company_name, data.industry, data.admin_name,
        str(data.admin_email), data.admin_password,
    )
    return TokenResponse(
        access_token=create_access_token(admin.id, tenant.id),
        user=_user_info(admin, tenant),
    )


# ---- Login / Profil ----

@router.post("/api/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    query = db.query(User).filter(User.email == str(data.email).lower(), User.active.is_(True))
    if data.tenant_slug:
        query = query.join(Tenant, Tenant.id == User.tenant_id).filter(
            Tenant.slug == data.tenant_slug
        )
    candidates = query.all()
    if len(candidates) > 1:
        raise HTTPException(409, "E-Mail existiert in mehreren Firmen — bitte tenant_slug angeben")

    user = candidates[0] if candidates else None
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "E-Mail oder Passwort falsch")

    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(403, "Firma ist deaktiviert")

    return TokenResponse(
        access_token=create_access_token(user.id, user.tenant_id),
        user=_user_info(user, tenant),
    )


@router.get("/api/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tenant = db.get(Tenant, user.tenant_id)
    permissions = [
        {"module": p.module, "action": p.action} for p in user.role.permissions
    ]
    return {**_user_info(user, tenant), "permissions": permissions}
