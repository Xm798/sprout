import datetime
import os
from pathlib import Path

import pytest
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
    if engine.dialect.name != "sqlite":
        SQLModel.metadata.drop_all(engine)


def new_schedule_payload(**over):
    """Canonical two-leg schedule body for API tests; override fields via kwargs."""
    body = {
        "name": "Spotify", "narration": "sub",
        "postings": [
            {"id": "main", "account": "Expenses:Subscription", "amount": "15.00",
             "currency": "USD", "cost": None, "price": None},
            {"id": "bal", "account": "Assets:CreditCard", "amount": None,
             "currency": None, "cost": None, "price": None},
        ],
        "interval_unit": "month", "interval_count": 1,
        "anchor_date": "2026-01-15", "max_count": 6, "tags": "sprout",
        "status": "active",
    }
    body.update(over)
    return body


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


@pytest.fixture
def tmp_ledger_config(config, tmp_path, demo_ledger) -> AppConfig:
    """Like `config`, but the main ledger is a copy under tmp_path so tests
    that append include lines to it cannot mutate repo files."""
    main = tmp_path / "main.bean"
    main.write_text(Path(demo_ledger).read_text())
    config.ledger_main_file = str(main)
    return config
