from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.api.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.sqlalchemy_database_uri(),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy Session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
