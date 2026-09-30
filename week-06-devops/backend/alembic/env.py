"""Alembic environment.

The connection URL comes from the application's own settings, not from
alembic.ini, so a migration can never run against a different database than
the one the service reads.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from config import get_settings
from models import Base

# Rebinds the name imported above; only get_settings is needed from that module.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # create_engine rather than engine_from_config: the URL holds a password
    # that ConfigParser would try to interpolate if it contained a percent sign.
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
