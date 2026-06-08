import os

from sqlmodel import SQLModel, Session, create_engine

from app.config import AppConfig, config_from_env
from app import models  # noqa: F401  ensure tables are registered

DB_PATH = os.getenv("SPROUT_DB_PATH", "sprout.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


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
