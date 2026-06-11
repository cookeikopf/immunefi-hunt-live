"""Passwort-Hashing (bcrypt) und JWT-Erstellung/-Prüfung (PyJWT)."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from ...core.config import get_settings

settings = get_settings()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, tenant_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "tid": tenant_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.token_expire_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
