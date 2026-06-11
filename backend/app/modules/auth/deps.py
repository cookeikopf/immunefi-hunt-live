"""FastAPI-Dependencies für Authentifizierung und Berechtigungsprüfung."""

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ...core.database import get_db
from .models import RolePermission, User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(401, "Ungültiges oder abgelaufenes Token",
                            headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.active or user.tenant_id != payload["tid"]:
        raise HTTPException(401, "Benutzer nicht gefunden oder deaktiviert",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def get_tenant_db(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Session:
    """Mandanten-gebundene Session: alle Queries werden automatisch gefiltert."""
    db.info["tenant_id"] = user.tenant_id
    return db


def has_permission(db: Session, user: User, module: str, action: str) -> bool:
    permissions = (
        db.query(RolePermission).filter(RolePermission.role_id == user.role_id).all()
    )
    for perm in permissions:
        if perm.module in ("*", module) and (perm.action == "write" or action == "read"):
            return True
    return False


def require_module(module: str):
    """Dependency-Factory: prüft die Berechtigung für ein Modul.

    Die Aktion ergibt sich aus der HTTP-Methode (GET/HEAD/OPTIONS = read,
    alles andere = write).
    """

    def checker(
        request: Request,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> None:
        action = "read" if request.method in READ_METHODS else "write"
        if not has_permission(db, user, module, action):
            raise HTTPException(403, f"Keine Berechtigung für {module}:{action}")

    return checker
