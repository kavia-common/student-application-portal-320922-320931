from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, EmailStr


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human readable error message")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type (always 'bearer')")


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    roles: list[str] = Field(default_factory=list)


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email (used as login)")
    password: str = Field(..., min_length=8, description="Plain password (min 8 chars)")
    first_name: str = Field(..., min_length=1, description="Student first name")
    last_name: str = Field(..., min_length=1, description="Student last name")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


ApplicationStatus = Literal[
    "draft",
    "submitted",
    "in_review",
    "needs_info",
    "approved",
    "rejected",
    "withdrawn",
]


class ApplicationCreate(BaseModel):
    program: str = Field(..., description="Program applying to")
    term: str = Field(..., description="Term (e.g. Fall 2026)")


class ApplicationUpdate(BaseModel):
    program: str | None = Field(None, description="Program applying to")
    term: str | None = Field(None, description="Term (e.g. Fall 2026)")


class ApplicationPublic(BaseModel):
    id: uuid.UUID
    student_user_id: uuid.UUID
    program: str
    term: str
    status: ApplicationStatus
    submitted_at: datetime | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SubmitApplicationResponse(BaseModel):
    application: ApplicationPublic


class StatusTransitionRequest(BaseModel):
    to_status: ApplicationStatus = Field(..., description="New status value")
    reason: str | None = Field(None, description="Optional reason for audit trail")


class AdminNoteCreate(BaseModel):
    note: str = Field(..., min_length=1, description="Note body")
    is_internal: bool = Field(True, description="Internal note (not visible to students)")


class AdminNotePublic(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    note: str
    is_internal: bool
    created_by_user_id: uuid.UUID | None
    created_at: datetime


class NotificationPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    body: str
    data: dict[str, Any] | None
    is_read: bool
    created_at: datetime
