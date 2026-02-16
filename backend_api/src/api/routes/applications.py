from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.core.db import get_db
from src.api.core.security import get_current_user, require_roles
from src.api.models import Application, ApplicationStatusHistory, Notification, User
from src.api.schemas import (
    ApplicationCreate,
    ApplicationPublic,
    ApplicationUpdate,
    SubmitApplicationResponse,
)

router = APIRouter(prefix="/applications", tags=["Student Applications"])


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


@router.get(
    "/my",
    response_model=list[ApplicationPublic],
    summary="List my applications",
    description="Lists applications owned by the authenticated student.",
)
def list_my_applications(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student"})),
) -> list[ApplicationPublic]:
    apps = (
        db.execute(
            select(Application)
            .where(Application.student_user_id == user.id)
            .order_by(Application.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_to_public(a) for a in apps]


@router.post(
    "",
    response_model=ApplicationPublic,
    status_code=201,
    summary="Create a new application (draft)",
    description="Creates a draft application for the authenticated student.",
)
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student"})),
) -> ApplicationPublic:
    now = datetime.now(timezone.utc)
    app = Application(
        student_user_id=user.id,
        program=payload.program,
        term=payload.term,
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return _to_public(app)


@router.get(
    "/{application_id}",
    response_model=ApplicationPublic,
    summary="Get my application by id",
    description="Fetches a single application owned by the authenticated student.",
)
def get_my_application(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student"})),
) -> ApplicationPublic:
    app = db.get(Application, application_id)
    if not app or app.student_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    return _to_public(app)


@router.patch(
    "/{application_id}",
    response_model=ApplicationPublic,
    summary="Update a draft application",
    description="Allows students to update program/term while in 'draft' or 'needs_info'.",
)
def update_application(
    application_id: str,
    payload: ApplicationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student"})),
) -> ApplicationPublic:
    app = db.get(Application, application_id)
    if not app or app.student_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status not in ("draft", "needs_info"):
        raise HTTPException(status_code=409, detail="Application cannot be edited in current status")

    if payload.program is not None:
        app.program = payload.program
    if payload.term is not None:
        app.term = payload.term

    app.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(app)
    return _to_public(app)


@router.post(
    "/{application_id}/submit",
    response_model=SubmitApplicationResponse,
    summary="Submit an application",
    description="Transitions application from 'draft' or 'needs_info' to 'submitted' and logs status history + notification.",
)
def submit_application(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student"})),
) -> SubmitApplicationResponse:
    app = db.get(Application, application_id)
    if not app or app.student_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status not in ("draft", "needs_info"):
        raise HTTPException(status_code=409, detail="Only draft/needs_info applications can be submitted")

    from_status = app.status
    now = datetime.now(timezone.utc)
    app.status = "submitted"
    app.submitted_at = now
    app.updated_at = now

    db.add(
        ApplicationStatusHistory(
            application_id=app.id,
            from_status=from_status,
            to_status="submitted",
            changed_by_user_id=user.id,
            reason="Student submitted application",
        )
    )

    db.add(
        Notification(
            user_id=user.id,
            type="application_submitted",
            title="Application submitted",
            body=f"Your application {app.id} was submitted successfully.",
            data={"application_id": str(app.id)},
            is_read=False,
        )
    )

    db.commit()
    db.refresh(app)
    return SubmitApplicationResponse(application=_to_public(app))


@router.post(
    "/{application_id}/withdraw",
    response_model=ApplicationPublic,
    summary="Withdraw an application",
    description="Allows a student to withdraw an application unless it is already approved/rejected.",
)
def withdraw_application(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles({"student"})),
) -> ApplicationPublic:
    app = db.get(Application, application_id)
    if not app or app.student_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")

    if app.status in ("approved", "rejected", "withdrawn"):
        raise HTTPException(status_code=409, detail="Application cannot be withdrawn in current status")

    from_status = app.status
    now = datetime.now(timezone.utc)
    app.status = "withdrawn"
    app.updated_at = now

    db.add(
        ApplicationStatusHistory(
            application_id=app.id,
            from_status=from_status,
            to_status="withdrawn",
            changed_by_user_id=user.id,
            reason="Student withdrew application",
        )
    )

    db.add(
        Notification(
            user_id=user.id,
            type="application_withdrawn",
            title="Application withdrawn",
            body=f"Your application {app.id} was withdrawn.",
            data={"application_id": str(app.id)},
            is_read=False,
        )
    )

    db.commit()
    db.refresh(app)
    return _to_public(app)


@router.get(
    "/health/auth",
    summary="Authenticated health check",
    description="Simple endpoint to verify JWT auth is working.",
)
def auth_health(user: User = Depends(get_current_user)) -> dict:
    return {"ok": True, "user_id": str(user.id)}
