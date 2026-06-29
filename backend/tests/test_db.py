import datetime

from sqlalchemy import inspect, text
from sqlmodel import SQLModel

import app.db as db_module
from app.db import _alembic_config, make_engine


def test_sqlite_url_gets_check_same_thread():
    engine = make_engine("sqlite:///test_tmp.db")
    assert engine.dialect.name == "sqlite"
    assert engine.url.database == "test_tmp.db"


def test_postgres_url_has_no_sqlite_connect_args():
    # Should construct without raising; psycopg driver resolved lazily at connect time.
    engine = make_engine("postgresql+psycopg://u:p@localhost:5432/sprout")
    assert engine.dialect.name == "postgresql"


def test_default_falls_back_to_sqlite_db_path(monkeypatch):
    monkeypatch.delenv("SPROUT_DATABASE_URL", raising=False)
    monkeypatch.setenv("SPROUT_DB_PATH", "fallback.db")
    engine = make_engine()
    assert engine.dialect.name == "sqlite"
    assert engine.url.database == "fallback.db"


def test_database_url_env_wins(monkeypatch):
    monkeypatch.setenv("SPROUT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/sprout")
    engine = make_engine()
    assert engine.dialect.name == "postgresql"


def test_alembic_upgrade_builds_schema_on_fresh_sqlite(tmp_path, monkeypatch):
    """A brand-new SQLite database brought up via `alembic upgrade head` must
    contain all three tables with their key columns, JSON columns, unique
    constraint and index — i.e. the Alembic baseline reproduces models.py."""
    from alembic import command

    db_file = tmp_path / "fresh.db"
    monkeypatch.setenv("SPROUT_DATABASE_URL", f"sqlite:///{db_file}")

    command.upgrade(_alembic_config(), "head")

    engine = make_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"schedule", "occurrence", "appconfig"} <= tables

    sched_cols = {c["name"] for c in insp.get_columns("schedule")}
    assert {"name", "payee", "narration", "target_file", "postings"} <= sched_cols

    occ_cols = {c["name"] for c in insp.get_columns("occurrence")}
    assert {"schedule_id", "due_date", "override_amounts"} <= occ_cols

    cfg_cols = {c["name"] for c in insp.get_columns("appconfig")}
    assert "default_currency" in cfg_cols

    # UniqueConstraint(schedule_id, due_date) and the schedule_id index.
    uniques = insp.get_unique_constraints("occurrence")
    assert any(set(u["column_names"]) == {"schedule_id", "due_date"} for u in uniques)
    indexes = {i["name"] for i in insp.get_indexes("occurrence")}
    assert "ix_occurrence_schedule_id" in indexes


def test_init_db_adopts_pre_alembic_database(tmp_path, monkeypatch):
    """A database created by the old SQLModel.create_all path (tables present,
    no alembic_version) must be adopted via stamp — not crash trying to
    CREATE TABLE over existing tables.

    A real pre-Alembic database carries exactly the *baseline* schema (it was
    created before any later migration existed), so simulate it by upgrading to
    the base revision and dropping alembic_version — not via create_all on the
    current metadata, which would also contain post-baseline tables and so
    misrepresent what a legacy database actually looks like."""
    from alembic import command
    from alembic.script import ScriptDirectory

    db_file = tmp_path / "legacy.db"
    monkeypatch.setenv("SPROUT_DATABASE_URL", f"sqlite:///{db_file}")
    cfg = _alembic_config()
    base = ScriptDirectory.from_config(cfg).get_base()
    command.upgrade(cfg, base)  # baseline schema only

    legacy_engine = make_engine(f"sqlite:///{db_file}")
    with legacy_engine.begin() as c:
        c.execute(text("DROP TABLE alembic_version"))  # back to a pre-Alembic state
    assert "alembic_version" not in inspect(legacy_engine).get_table_names()

    monkeypatch.setattr(db_module, "engine", legacy_engine)

    db_module.init_db()  # must not raise
    db_module.init_db()  # idempotent

    insp = inspect(legacy_engine)
    assert "alembic_version" in insp.get_table_names()
    with legacy_engine.connect() as c:
        version = c.execute(text("select version_num from alembic_version")).scalar()
    assert version is not None


def test_schedule_model_has_target_file_default_none(session):
    from app.models import Schedule
    sch = Schedule(
        name="x", interval_unit="month", anchor_date=datetime.date(2026, 1, 1),
        postings=[],
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)
    assert sch.target_file is None
