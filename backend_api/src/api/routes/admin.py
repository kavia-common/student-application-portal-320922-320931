from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from src.api.core.db import get_db
from src.api.core.security import require_roles
from src.api.models import (
    AdminNote,
    Application,
    ApplicationStatusHistory,
    Notification,
    User,
)
from src.api.schemas import (
    AdminNoteCreate,
    AdminNotePublic,
    ApplicationPublic,
    ApplicationStatus,
    StatusTransitionRequest,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


def _to_public(app: Application) -> ApplicationPublic:
    return ApplicationPublic(
        id=app.id,
        student_user_id=app.student_user_id,
        program=app.program,
        term=app.term,
        status=app.status,  # type: ignore[arg-type]
        submitted_at=app.submitted_at,
        decided_at=app.decided_at,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def _to_note_public(n: AdminNote) -> AdminNotePublic:
    return AdminNotePublic(
        id=n.id,
        application_id=n.application_id,
        note=n.note,
        is_internal=n.is_internal,
        created_by_user_id=n.created_by_user_id,
        created_at=n.created_at,
    )


_ALLOWED_ADMIN_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    "submitted": {"in_review", "needs_info", "rejected"},
    "in_review": {"needs_info", "approved", "rejected"},
    "needs_info": {"in_review", "rejected"},
    "draft": {"rejected"},
    "withdrawn": set(),
    "approved": set(),
    "rejected": set(),
}


@router.get(
    "/applications",
    response_model=list[ApplicationPublic],
    summary="Admin list applications",
    description="List applications with optional filtering by status and search by program/term/student id.",
)
def admin_list_applications(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({"admin"})),
    status_filter: ApplicationStatus | None = Query(None, alias="status", description="Filter by status"),
    q: str | None = Query(None, description="Free text search on program/term or student id"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ApplicationPublic]:
    stmt = select(Application)

    where = []
    if status_filter:
        where.append(Application.status == status_filter)
    if q:
        like = f"%{q}%"
        where.append(
            or_(
                Application.program.ilike(like),
                Application.term.ilike(like),
                Application.student_user_id.cast(str).ilike(like),
            )
        )
    if where:
        stmt = stmt.where(and_(*where))

    apps = db.execute(stmt.order_by(Application.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return [_to_public(a) for a in apps]


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationPublic,
    summary="Admin get application detail",
    description="Fetch an application by id for review.",
)
def admin_get_application(
    application_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({"admin"})),
) -> ApplicationPublic:
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return _to_public(app)


@router.post(
    "/applications/{application_id}/status",
    response_model=ApplicationPublic,
    summary="Admin change application status",
    description="Transitions status with validation, writes status history, sets decided_at for approved/rejected, and creates a notification for the student.",
)
def admin_change_status(
    application_id: str,
    payload: StatusTransitionRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_roles({"admin"})),
) -> ApplicationPublic:
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    current = app.status  # type: ignore[assignment]
    allowed = _ALLOWED_ADMIN_TRANSITIONS.get(current, set())
    if payload.to_status not in allowed:
        raise HTTPException(status_code=409, detail=f"Invalid transition from {current} to {payload.to_status}")

    now = datetime.now(timezone.utc)
    app.status = payload.to_status
    app.updated_at = now

    if payload.to_status in ("approved", "rejected"):
        app.decided_at = now

    db.add(
        ApplicationStatusHistory(
            application_id=app.id,
            from_status=current,
            to_status=payload.to_status,
            changed_by_user_id=admin_user.id,
            reason=payload.reason,
        )
    )

    db.add(
        Notification(
            user_id=app.student_user_id,
            type="application_status_changed",
            title="Application status updated",
            body=f"Your application status is now '{payload.to_status}'.",
            data={"application_id": str(app.id), "from": current, "to": payload.to_status, "reason": payload.reason},
            is_read=False,
        )
    )

    db.commit()
    db.refresh(app)
    return _to_public(app)


@router.post(
    "/applications/{application_id}/notes",
    response_model=AdminNotePublic,
    status_code=201,
    summary="Add admin note to application",
    description="Creates an internal (or external) note associated with an application.",
)
def admin_add_note(
    application_id: str,
    payload: AdminNoteCreate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_roles({"admin"})),
) -> AdminNotePublic:
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    note = AdminNote(
        application_id=app.id,
        note=payload.note,
        is_internal=payload.is_internal,
        created_by_user_id=admin_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(note)

    # If note is not internal, notify student (simple in-app notification log).
    if not payload.is_internal:
        db.add(
            Notification(
                user_id=app.student_user_id,
                type="application_note",
                title="New note on your application",
                body=payload.note,
                data={"application_id": str(app.id)},
                is_read=False,
            )
        )

    db.commit()
    db.refresh(note)
    return _to_note_public(note)


@router.get(
    "/applications/{application_id}/notes",
    response_model=list[AdminNotePublic],
    summary="List admin notes for an application",
    description="Lists notes in reverse chronological order.",
)
def admin_list_notes(
    application_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles({"admin"})),
) -> list[AdminNotePublic]:
    app = db.get(Application, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    notes = (
        db.execute(
            select(AdminNote)
            .where(AdminNote.application_id == app.id)
            .order_by(AdminNote.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_to_note_public(n) for n in notes]
