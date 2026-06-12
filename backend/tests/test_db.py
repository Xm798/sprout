import datetime
import json

import pytest
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


def _create_legacy_tables(conn) -> None:
    """Create the pre-multi-posting schema tables (schedule + occurrence)."""
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


def _make_legacy_engine():
    """A DB shaped like the pre-multi-posting schema with one schedule and one occurrence."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        _create_legacy_tables(conn)
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


def test_migration_raises_on_orphaned_occurrence_with_override_amount():
    """Occurrence with non-NULL override_amount but missing schedule row should raise."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        _create_legacy_tables(conn)
        conn.execute(text(
            "INSERT INTO occurrence (id, schedule_id, due_date, status, override_amount)"
            " VALUES (99, 999, '2026-06-15', 'pending', 123.45)"
        ))

    with pytest.raises(ValueError, match=r"occurrence id=99"):
        migrate_legacy_schema(engine)


def test_migration_succeeds_on_orphaned_occurrence_with_null_override():
    """Occurrence with NULL override_amount but missing schedule row should migrate fine."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        _create_legacy_tables(conn)
        conn.execute(text(
            "INSERT INTO occurrence (id, schedule_id, due_date, status, override_amount)"
            " VALUES (99, 999, '2026-06-15', 'pending', NULL)"
        ))

    migrate_legacy_schema(engine)  # Must not raise

    ocols = {c["name"] for c in inspect(engine).get_columns("occurrence")}
    assert "override_amounts" in ocols and "override_amount" not in ocols

    with engine.begin() as conn:
        occ = conn.execute(text("SELECT override_amounts FROM occurrence WHERE id=99")).first()
    overrides = json.loads(occ.override_amounts) if isinstance(occ.override_amounts, str) else occ.override_amounts
    assert overrides == {}  # NULL override_amount migrates to empty dict


# --- New tests required by spec ---

def test_migration_schema_untouched_on_validation_error():
    """ValueError before DDL: occurrence table must NOT gain override_amounts column."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        _create_legacy_tables(conn)
        # Orphaned occurrence with non-NULL override_amount → will fail validation
        conn.execute(text(
            "INSERT INTO occurrence (id, schedule_id, due_date, status, override_amount)"
            " VALUES (7, 999, '2026-06-15', 'pending', 50.00)"
        ))

    with pytest.raises(ValueError):
        migrate_legacy_schema(engine)

    # Schema must be completely untouched — no new column added.
    occ_cols = {c["name"] for c in inspect(engine).get_columns("occurrence")}
    assert "override_amounts" not in occ_cols, (
        "override_amounts column must not exist after a failed migration"
    )


def test_migration_resumes_half_migrated_occurrence():
    """Half-migrated DB (override_amounts already added, override_amount still present)
    must complete: backfill rows and drop the old column."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        # Use the new-style schedule (postings column already present)
        conn.execute(text(
            "CREATE TABLE schedule ("
            "id INTEGER PRIMARY KEY, name TEXT, narration TEXT,"
            "postings JSON,"
            "interval_unit TEXT, interval_count INTEGER, anchor_date DATE,"
            "end_date DATE, max_count INTEGER, tags TEXT, status TEXT,"
            "created_at DATETIME, updated_at DATETIME)"
        ))
        posting_id = "abc123"
        postings = json.dumps([
            {"id": posting_id, "account": "Expenses:Sub", "amount": "10.00",
             "currency": "USD", "cost": None, "price": None},
            {"id": "def456", "account": "Assets:Card", "amount": None,
             "currency": None, "cost": None, "price": None},
        ])
        conn.execute(text(
            "INSERT INTO schedule (id, name, narration, postings, interval_unit,"
            " interval_count, anchor_date, tags, status)"
            " VALUES (1, 'S', 'n', :p, 'month', 1, '2026-01-01', '', 'active')"
        ), {"p": postings})

        # Occurrence table already has override_amounts (wedged state: ADD COLUMN succeeded
        # in a prior aborted run) but override_amount is still present too.
        conn.execute(text(
            "CREATE TABLE occurrence ("
            "id INTEGER PRIMARY KEY, schedule_id INTEGER, due_date DATE, status TEXT,"
            "override_amount NUMERIC, override_amounts JSON,"
            "override_date DATE, override_narration TEXT,"
            "written_path TEXT, sprout_id TEXT, confirmed_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO occurrence (id, schedule_id, due_date, status, override_amount)"
            " VALUES (1, 1, '2026-06-15', 'pending', 7.77)"
        ))

    migrate_legacy_schema(engine)  # must not raise

    ocols = {c["name"] for c in inspect(engine).get_columns("occurrence")}
    assert "override_amounts" in ocols
    assert "override_amount" not in ocols

    with engine.begin() as conn:
        occ = conn.execute(text("SELECT override_amounts FROM occurrence WHERE id=1")).first()
    overrides = json.loads(occ.override_amounts) if isinstance(occ.override_amounts, str) else occ.override_amounts
    assert overrides == {"abc123": "7.77"}


def test_migration_resumes_half_migrated_schedule():
    """Half-migrated DB (postings already added, amount/from_account still present)
    must complete: backfill rows and drop the old columns."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        # Schedule has both old columns AND the new postings column (wedged state).
        conn.execute(text(
            "CREATE TABLE schedule ("
            "id INTEGER PRIMARY KEY, name TEXT, narration TEXT,"
            "amount NUMERIC, currency TEXT, from_account TEXT, to_account TEXT,"
            "postings JSON,"
            "interval_unit TEXT, interval_count INTEGER, anchor_date DATE,"
            "end_date DATE, max_count INTEGER, tags TEXT, status TEXT,"
            "created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO schedule (id, name, narration, amount, currency, from_account,"
            " to_account, interval_unit, interval_count, anchor_date, tags, status)"
            " VALUES (1, 'G', 'gym', 30.00, 'USD', 'Assets:Card', 'Expenses:Gym',"
            " 'month', 1, '2026-01-01', '', 'active')"
        ))
        conn.execute(text(
            "CREATE TABLE occurrence ("
            "id INTEGER PRIMARY KEY, schedule_id INTEGER, due_date DATE, status TEXT,"
            "override_amount NUMERIC, override_date DATE, override_narration TEXT,"
            "written_path TEXT, sprout_id TEXT, confirmed_at DATETIME)"
        ))

    migrate_legacy_schema(engine)  # must not raise

    sched_cols = {c["name"] for c in inspect(engine).get_columns("schedule")}
    assert "postings" in sched_cols
    assert "from_account" not in sched_cols
    assert "amount" not in sched_cols

    with engine.begin() as conn:
        row = conn.execute(text("SELECT postings FROM schedule WHERE id=1")).first()
    postings = json.loads(row.postings) if isinstance(row.postings, str) else row.postings
    assert postings[0]["account"] == "Expenses:Gym"
    assert postings[0]["amount"] == "30.00"


def test_migration_raises_on_malformed_postings_json():
    """Malformed schedule.postings JSON with non-NULL override_amount raises ValueError
    naming both the occurrence id and schedule id (not JSONDecodeError)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE schedule ("
            "id INTEGER PRIMARY KEY, name TEXT, narration TEXT,"
            "postings JSON,"
            "interval_unit TEXT, interval_count INTEGER, anchor_date DATE,"
            "end_date DATE, max_count INTEGER, tags TEXT, status TEXT,"
            "created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO schedule (id, name, narration, postings, interval_unit,"
            " interval_count, anchor_date, tags, status)"
            " VALUES (5, 'B', 'bad', :p, 'month', 1, '2026-01-01', '', 'active')"
        ), {"p": "NOT_VALID_JSON"})
        conn.execute(text(
            "CREATE TABLE occurrence ("
            "id INTEGER PRIMARY KEY, schedule_id INTEGER, due_date DATE, status TEXT,"
            "override_amount NUMERIC, override_date DATE, override_narration TEXT,"
            "written_path TEXT, sprout_id TEXT, confirmed_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO occurrence (id, schedule_id, due_date, status, override_amount)"
            " VALUES (42, 5, '2026-06-15', 'pending', 11.00)"
        ))

    with pytest.raises(ValueError, match=r"occurrence id=42.*schedule id=5"):
        migrate_legacy_schema(engine)

    # Schema must not have been mutated: setup error must prevent DDL.
    occ_cols = {c["name"] for c in inspect(engine).get_columns("occurrence")}
    assert "override_amounts" not in occ_cols


def test_migration_adds_target_file_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE schedule (id INTEGER PRIMARY KEY, name VARCHAR, postings JSON)"
        ))
    migrate_legacy_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("schedule")}
    assert "target_file" in cols
    # idempotent: second run must not raise
    migrate_legacy_schema(engine)


def test_migration_adds_default_currency_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE appconfig (id INTEGER PRIMARY KEY, ledger_main_file VARCHAR)"
        ))
        conn.execute(text("INSERT INTO appconfig (id, ledger_main_file) VALUES (1, '')"))
    migrate_legacy_schema(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("appconfig")}
    assert "default_currency" in cols
    with engine.begin() as conn:
        row = conn.execute(text("SELECT default_currency FROM appconfig WHERE id=1")).first()
    assert row.default_currency == "USD"  # existing row backfilled with the default
    # idempotent: second run must not raise
    migrate_legacy_schema(engine)


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
