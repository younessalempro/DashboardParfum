"""
app/db.py
=========
SQLAlchemy engine and session factory.

We use *synchronous* psycopg3 for v1 (simpler, no async overhead).
Switch to async later by swapping create_engine → create_async_engine
and Session → AsyncSession.

Usage
-----
    from app.db import get_session

    # In a FastAPI dependency:
    def endpoint(db: Session = Depends(get_session)):
        ...
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,       # reconnects if the connection dropped
    pool_size=5,
    max_overflow=10,
    echo=False,               # set True to see SQL in logs
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Declarative base — all models inherit from this
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_session() -> Generator[Session, None, None]:
    """Yield a DB session and guarantee it's closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Health check helper
# ---------------------------------------------------------------------------

def ping_db() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
