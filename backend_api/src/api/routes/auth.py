from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.core.db import get_db
from src.api.core.security import (
    create_access_token,
    get_current_user,
    get_user_roles,
    hash_password,
    verify_password,
)
from src.api.models import Role, StudentProfile, User, UserRole
from src.api.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=201,
    summary="Register a new student user",
    description="Creates a new user, a student profile, assigns the 'student' role, and returns a JWT.",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        is_active=True,
        is_email_verified=False,
    )
    db.add(user)
    db.flush()  # assigns user.id

    profile = StudentProfile(
        user_id=user.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        country="US",
    )
    db.add(profile)

    role = db.execute(select(Role).where(Role.name == "student")).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=500, detail="Role 'student' not configured in database")
    db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)

    roles = get_user_roles(db, user)
    token = create_access_token(user_id=user.id, roles=roles)
    return TokenResponse(access_token=token)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with email and password",
    description="Validates credentials and returns a JWT access token.",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    roles = get_user_roles(db, user)
    token = create_access_token(user_id=user.id, roles=roles)
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get current user",
    description="Returns the authenticated user's id/email and role names.",
)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserPublic:
    roles = get_user_roles(db, user)
    return UserPublic(id=user.id, email=user.email, roles=roles)
