from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


def normalize_database_url(url: str) -> str:
    """Upgrade a bare `postgresql://` URL to the psycopg v3 driver.

    SQLAlchemy resolves a bare `postgresql://` URL to its default psycopg2
    dialect. This project standardized on psycopg v3 (see requirements.txt),
    so rewrite the driver part for bare URLs instead of failing with
    "No module named 'psycopg2'". Explicit driver choices are preserved.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


settings = get_settings()
engine = create_engine(normalize_database_url(settings.DATABASE_URL), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
