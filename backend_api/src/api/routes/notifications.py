from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.core.db import get_db
from src.api.core.security import require_roles
from src.api.models import Notification, User
from src.api.schemas import NotificationPublic

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _to_public(n: Notification) -> NotificationPublic:
    return NotificationPublic(
        id=n.id,
        user_id=n.user_id,
        type=n.type,
        title=n.title,
        body=n.body,
        data=n.data,
        is_read=n.is_read,
        created_at=n.created_at,
    )


@router.get(
    "/my",
    response_model=list[NotificationPublic],
    summary="List my notifications",
    description="Lists in-app notifications for the authenticated student.",
)
def list_my_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student"})),
    unread_only: bool = Query(False, description="If true, return only unread notifications"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[NotificationPublic]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    notes = (
        db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [_to_public(n) for n in notes]


@router.post(
    "/{notification_id}/read",
    response_model=NotificationPublic,
    summary="Mark notification as read",
    description="Marks a notification as read (must belong to current user).",
)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student", "admin"})),
) -> NotificationPublic:
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")

    n.is_read = True
    db.commit()
    db.refresh(n)
    return _to_public(n)
