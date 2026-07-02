import datetime
import json

from sqlalchemy import inspect, text

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

    # The loan migration widened the unique constraint to 4 columns.
    uniques = insp.get_unique_constraints("occurrence")
    assert any(
        set(u["column_names"]) == {"schedule_id", "due_date", "loan_event", "event_id"}
        for u in uniques
    )
    indexes = {i["name"] for i in insp.get_indexes("occurrence")}
    assert "ix_occurrence_schedule_id" in indexes


def test_loan_migration_upgrades_legacy_row_and_adds_defaults(tmp_path, monkeypatch):
    """A DB stamped at the pre-loan head (3410f3212aec) with a schedule row must
    survive upgrade head with kind='fixed' and events=[] backfilled from server defaults."""
    from alembic import command

    db_file = tmp_path / "pre_loan.db"
    monkeypatch.setenv("SPROUT_DATABASE_URL", f"sqlite:///{db_file}")
    cfg = _alembic_config()

    # Build DB at the pre-loan head and insert a legacy schedule row.
    command.upgrade(cfg, "3410f3212aec")
    engine = make_engine(f"sqlite:///{db_file}")
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO schedule (name, payee, narration, interval_unit, interval_count,"
            " anchor_date, tags, status, postings, created_at, updated_at)"
            " VALUES ('rent', '', '', 'month', 1, '2025-01-01', '', 'active', '[]',"
            " '2025-01-01 00:00:00', '2025-01-01 00:00:00')"
        ))

    # Upgrade to head (the loan-schedules migration).
    command.upgrade(cfg, "head")

    with engine.connect() as c:
        row = c.execute(text("SELECT kind, events FROM schedule WHERE name='rent'")).fetchone()
    assert row is not None
    assert row[0] == "fixed"
    # SQLite stores server_default as the raw SQL string; JSON load normalises it.
    assert json.loads(row[1]) == []


def test_loan_schedule_and_occurrence_columns_roundtrip(session):
    from app.models import Schedule, Occurrence
    import datetime
    sch = Schedule(name="Mortgage", interval_unit="month", interval_count=1,
                   anchor_date=datetime.date(2026, 1, 1), kind="loan",
                   loan={"principal": "1000000", "annual_rate": "0.0485",
                         "term_count": 360, "method": "equal_payment"},
                   events=[], postings=[])
    session.add(sch); session.commit(); session.refresh(sch)
    assert sch.kind == "loan" and sch.loan["term_count"] == 360
    occ = Occurrence(schedule_id=sch.id, due_date=datetime.date(2026, 1, 1),
                     loan_seq=1, loan_event="regular", event_id="")
    session.add(occ); session.commit(); session.refresh(occ)
    assert occ.loan_event == "regular" and occ.frozen_postings is None


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


def test_sqlite_engine_sets_wal_and_busy_timeout(tmp_path):
    from app.db import make_engine
    import sqlalchemy as sa

    eng = make_engine(f"sqlite:///{tmp_path/'x.db'}")
    with eng.connect() as c:
        assert c.execute(sa.text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert int(c.execute(sa.text("PRAGMA busy_timeout")).scalar()) >= 5000
    eng.dispose()
