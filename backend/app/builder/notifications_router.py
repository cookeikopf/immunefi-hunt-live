"""Mitteilungen: an Benutzer oder Rollen gerichtete interne Nachrichten."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..modules.auth.deps import get_current_user, get_tenant_db
from ..modules.auth.models import User
from .models import Notification

router = APIRouter(prefix="/api/notifications", tags=["Mitteilungen"])


def _visible(query, user: User):
    from sqlalchemy import or_

    return query.filter(or_(
        Notification.user_id == user.id,
        Notification.role_name == user.role.name,
        Notification.role_name == "Admin" if user.role.name == "Admin" else False,
    ))


@router.get("")
def list_notifications(
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    query = _visible(db.query(Notification), user)
    if unread_only:
        query = query.filter(Notification.read.is_(False))
    items = query.order_by(Notification.created_at.desc()).limit(100).all()
    return [
        {"id": n.id, "message": n.message, "source": n.source,
         "read": n.read, "created_at": n.created_at}
        for n in items
    ]


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_tenant_db),
):
    notification = _visible(
        db.query(Notification).filter(Notification.id == notification_id), user
    ).first()
    if notification is None:
        raise HTTPException(404, "Mitteilung nicht gefunden")
    notification.read = True
    db.commit()
    return {"ok": True}
