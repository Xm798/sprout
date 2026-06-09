import os

from sqlalchemy.engine import make_url
from sqlmodel import SQLModel, Session, create_engine

from app.config import AppConfig, config_from_env
from app import models  # noqa: F401  ensure tables are registered


def _resolve_url(url: str | None) -> str:
    if url:
        return url
    db_path = os.getenv("SPROUT_DB_PATH", "sprout.db")
    return f"sqlite:///{db_path}"


def make_engine(url: str | None = None):
    resolved = _resolve_url(url or os.getenv("SPROUT_DATABASE_URL"))
    connect_args = {}
    if make_url(resolved).get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
    return create_engine(resolved, connect_args=connect_args)


engine = make_engine()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        existing = session.get(AppConfig, 1)
        if existing is None:
            session.add(config_from_env())
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
