"""Engine, session factory, and the FastAPI request-scoped session.

Everything here is built lazily for the same reason config.get_settings() is:
importing this module must not require a populated .env or a running database,
or the Part D tests could not import the application.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from config import get_settings

# Below the HEALTHCHECK's 2.5 s request timeout, so a hung connect answers DOWN before the probe gives up.
DB_CONNECT_TIMEOUT_SECONDS = 2


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """One connection pool per process."""
    return create_engine(
        get_settings().database_url,
        # Checks a pooled connection before handing it out. Without this, the
        # first request after the database container restarts fails on a
        # connection the pool still believes is alive.
        pool_pre_ping=True,
        # Bounds opening a new connection only; a pooled connection to a frozen database
        # can still hang until the gateway's 30 s timeout (see get_probe_engine).
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    )


@lru_cache(maxsize=1)
def get_probe_engine() -> Engine:
    """Unpooled, so every health check opens a fresh connection bounded by the connect timeout."""
    # A pooled connection to a database that stopped answering would hang past that timeout.
    return create_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
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
