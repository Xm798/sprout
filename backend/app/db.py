import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine

from app.config import AppConfig, config_from_env
from app import models  # noqa: F401  ensure tables are registered


def _resolve_url(url: str | None) -> str:
    if url:
        return url
    db_path = os.getenv("SPROUT_DB_PATH", "sprout.db")
    return f"sqlite:///{db_path}"


def resolve_database_url() -> str:
    """The database URL the app (and Alembic) target, from SPROUT_DATABASE_URL
    or the SPROUT_DB_PATH SQLite fallback. The single source of truth so the
    app engine and Alembic's env.py can never disagree."""
    return _resolve_url(os.getenv("SPROUT_DATABASE_URL"))


def is_sqlite_url(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def make_engine(url: str | None = None):
    resolved = _resolve_url(url) if url else resolve_database_url()
    connect_args = {}
    if is_sqlite_url(resolved):
        connect_args["check_same_thread"] = False
    return create_engine(resolved, connect_args=connect_args)


engine = make_engine()


def _alembic_config() -> Config:
    """Alembic config pinned to the backend's alembic.ini regardless of cwd.
    env.py resolves the database URL from the same SPROUT_* env logic as the app."""
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    return Config(str(ini_path))


def init_db() -> None:
    """Bring the database schema up to date by running Alembic migrations,
    then seed the singleton AppConfig row if it is missing."""
    command.upgrade(_alembic_config(), "head")
    with Session(engine) as session:
        existing = session.get(AppConfig, 1)
        if existing is None:
            session.add(config_from_env())
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session


def get_config(session: Session) -> AppConfig:
    """Fetch the singleton AppConfig row or fail the request with a 500."""
    cfg = session.get(AppConfig, 1)
    if cfg is None:
        raise HTTPException(500, "config not initialized")
    return cfg
