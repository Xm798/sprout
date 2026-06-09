import datetime
import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.config import AppConfig


def make_test_engine():
    """In-memory SQLite by default; honors SPROUT_TEST_DATABASE_URL for Postgres."""
    url = os.getenv("SPROUT_TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)
        return engine
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session():
    engine = make_test_engine()
    with Session(engine) as s:
        yield s
    if make_url(str(engine.url)).get_backend_name() != "sqlite":
        SQLModel.metadata.drop_all(engine)


@pytest.fixture
def demo_ledger() -> str:
    return str(Path(__file__).parent / "fixtures" / "demo.bean")


@pytest.fixture
def config(tmp_path, demo_ledger) -> AppConfig:
    return AppConfig(
        id=1,
        ledger_main_file=demo_ledger,
        ledger_root=str(tmp_path),
        write_mode="single_file",
        single_file_name="sprout.bean",
        default_tag="sprout",
        lookahead_days=0,
    )


@pytest.fixture
def today() -> datetime.date:
    return datetime.date(2026, 6, 8)
