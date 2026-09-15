"""Engine, session factory, and the FastAPI request-scoped session.

Everything here is built lazily for the same reason config.get_settings() is:
importing this module must not require a populated .env or a running database,
or the Part D tests could not import the application.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """One connection pool per process."""
    return create_engine(
        get_settings().database_url,
        # Checks a pooled connection before handing it out. Without this, the
        # first request after the database container restarts fails on a
        # connection the pool still believes is alive.
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


# Week 2's create_tables() has been removed: Alembic owns the schema from here,
# because create_all only adds tables and Week 3 alters an existing one.


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
