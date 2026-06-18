from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context

# Import the app's models so every table is registered on SQLModel.metadata,
# and reuse the app's URL/engine resolution so Alembic and the app always agree
# on which database they target (SPROUT_DATABASE_URL / SPROUT_DB_PATH).
from app import models  # noqa: F401  ensure tables are registered
from app.db import is_sqlite_url, make_engine, resolve_database_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# SQLite cannot ALTER columns/constraints in place; batch mode emits the
# copy-and-rename table rebuild that makes later migrations portable.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite_url(url),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = make_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
