import json

from sqlalchemy import text, inspect
from sqlmodel import create_engine

from app.db import make_engine, migrate_legacy_schema


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


def _make_legacy_engine():
    """A DB shaped like the pre-multi-posting schema."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE schedule ("
            "id INTEGER PRIMARY KEY, name TEXT, narration TEXT,"
            "amount NUMERIC, currency TEXT, from_account TEXT, to_account TEXT,"
            "interval_unit TEXT, interval_count INTEGER, anchor_date DATE,"
            "end_date DATE, max_count INTEGER, tags TEXT, status TEXT,"
            "created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "CREATE TABLE occurrence ("
            "id INTEGER PRIMARY KEY, schedule_id INTEGER, due_date DATE, status TEXT,"
            "override_amount NUMERIC, override_date DATE, override_narration TEXT,"
            "written_path TEXT, sprout_id TEXT, confirmed_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO schedule (id, name, narration, amount, currency,"
            " from_account, to_account, interval_unit, interval_count, anchor_date,"
            " tags, status) VALUES "
            "(1, 'Spotify', 'sub', 15.00, 'USD', 'Assets:CreditCard',"
            " 'Expenses:Subscription', 'month', 1, '2026-01-15', 'sprout', 'active')"
        ))
        conn.execute(text(
            "INSERT INTO occurrence (id, schedule_id, due_date, status, override_amount)"
            " VALUES (1, 1, '2026-06-15', 'pending', 9.99)"
        ))
    return engine


def test_migration_rewrites_legacy_schedule():
    engine = _make_legacy_engine()
    migrate_legacy_schema(engine)

    cols = {c["name"] for c in inspect(engine).get_columns("schedule")}
    assert "postings" in cols
    assert "from_account" not in cols and "amount" not in cols

    with engine.begin() as conn:
        row = conn.execute(text("SELECT postings FROM schedule WHERE id=1")).first()
    postings = json.loads(row.postings) if isinstance(row.postings, str) else row.postings
    assert postings[0]["account"] == "Expenses:Subscription"
    assert postings[0]["amount"] == "15.00"
    assert postings[1]["account"] == "Assets:CreditCard"
    assert postings[1]["amount"] is None
    assert postings[0]["id"] and postings[1]["id"]


def test_migration_rewrites_legacy_occurrence_override():
    engine = _make_legacy_engine()
    migrate_legacy_schema(engine)

    ocols = {c["name"] for c in inspect(engine).get_columns("occurrence")}
    assert "override_amounts" in ocols and "override_amount" not in ocols

    with engine.begin() as conn:
        occ = conn.execute(text("SELECT override_amounts FROM occurrence WHERE id=1")).first()
        sch = conn.execute(text("SELECT postings FROM schedule WHERE id=1")).first()
    overrides = json.loads(occ.override_amounts) if isinstance(occ.override_amounts, str) else occ.override_amounts
    postings = json.loads(sch.postings) if isinstance(sch.postings, str) else sch.postings
    assert overrides == {postings[0]["id"]: "9.99"}


def test_migration_idempotent_and_noop_on_fresh():
    engine = _make_legacy_engine()
    migrate_legacy_schema(engine)
    migrate_legacy_schema(engine)  # second run must not raise
    cols = {c["name"] for c in inspect(engine).get_columns("schedule")}
    assert "postings" in cols


def test_migration_noop_on_fresh_schema():
    from sqlmodel import SQLModel
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    migrate_legacy_schema(engine)  # fresh new-schema DB: must be a no-op, no raise
    cols = {c["name"] for c in inspect(engine).get_columns("schedule")}
    assert "postings" in cols and "from_account" not in cols
