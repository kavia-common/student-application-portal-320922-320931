from __future__ import annotations

from collections.abc import Generator
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.api.core.config import get_settings

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _init_engine_and_sessionmaker() -> None:
    """Initialize SQLAlchemy engine/sessionmaker once, on first DB use."""
    global _engine, _SessionLocal
    if _engine is not None and _SessionLocal is not None:
        return

    settings = get_settings()
    # This may raise if DB env vars are missing; that's OK as long as endpoints that
    # require DB access aren't called. It should not prevent the server from starting.
    _engine = create_engine(
        settings.sqlalchemy_database_uri(),
        pool_pre_ping=True,
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


# PUBLIC_INTERFACE
def SessionLocal() -> Session:
    """Create and return a new SQLAlchemy Session.

    This is intentionally lazy-initialized so the API can start in preview environments
    even if DB env vars are not present yet.
    """
    _init_engine_and_sessionmaker()
    assert _SessionLocal is not None  # for type checkers
    return _SessionLocal()  # type: ignore[misc]


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy Session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
