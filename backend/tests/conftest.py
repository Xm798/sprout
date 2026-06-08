import datetime
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

from app.config import AppConfig


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


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
