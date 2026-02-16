from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.core.config import get_settings
from src.api.core.db import get_db
from src.api.models import Role, User

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plain password using bcrypt."""
    return pwd_context.hash(password)


# PUBLIC_INTERFACE
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


# PUBLIC_INTERFACE
def create_access_token(*, user_id: uuid.UUID, roles: list[str]) -> str:
    """Create a signed JWT access token containing the user id and roles."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        ) from e


# PUBLIC_INTERFACE
def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    """FastAPI dependency that returns the authenticated user."""
    payload = _decode_token(token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        user_id = uuid.UUID(sub)
    except ValueError as e:
        raise HTTPException(status_code=401, detail="Invalid user id in token") from e

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


# PUBLIC_INTERFACE
def require_roles(required_roles: set[str]):
    """
    Dependency factory: require the current user to have at least one of required_roles.
    """

    def _dep(user: User = Depends(get_current_user)) -> User:
        user_roles = {r.name for r in (user.roles or [])}
        if not (user_roles & required_roles):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _dep


# PUBLIC_INTERFACE
def get_user_roles(db: Session, user: User) -> list[str]:
    """Return role names for a user (selectin-loaded, but safe fallback)."""
    if user.roles is not None:
        return [r.name for r in user.roles]

    # Fallback: load roles explicitly
    stmt = (
        select(Role.name)
        .join_from(User, User.roles)
        .where(User.id == user.id)
    )
    return [row[0] for row in db.execute(stmt).all()]
