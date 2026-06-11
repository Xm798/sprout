import json
import os
import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import inspect, text
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


def _dec_str(value) -> str:
    """Canonical 2-decimal storage form for migrated legacy amounts.
    Always produces at least 2 decimal places (e.g. 15 → '15.00'), which differs
    from bean_format render that omits trailing zeros (e.g. '15')."""
    s = format(Decimal(str(value)), "f")
    if "." in s:
        integer_part, frac_part = s.split(".")
        return f"{integer_part}.{frac_part.rstrip('0').ljust(2, '0')}"
    return f"{s}.00"


def _columns(engine, table: str) -> set[str]:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _migrate_schedule(engine) -> None:
    sched_cols = _columns(engine, "schedule")

    # Validation pass: read all rows and compute updates before any DDL.
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, amount, currency, from_account, to_account FROM schedule"
        )).all()

    updates: list[tuple[str, int]] = []  # (json_str, row_id)
    for r in rows:
        if r.amount is None:
            raise ValueError(
                f"schedule id={r.id}: NULL amount cannot be migrated; "
                "set a valid amount before upgrading."
            )
        postings = [
            {"id": uuid.uuid4().hex, "account": r.to_account,
             "amount": _dec_str(r.amount), "currency": r.currency,
             "cost": None, "price": None},
            {"id": uuid.uuid4().hex, "account": r.from_account,
             "amount": None, "currency": None, "cost": None, "price": None},
        ]
        updates.append((json.dumps(postings), r.id))

    # All rows validated — now mutate the schema.
    with engine.begin() as conn:
        if "postings" not in sched_cols:
            conn.execute(text("ALTER TABLE schedule ADD COLUMN postings JSON"))
        for p, row_id in updates:
            conn.execute(
                text("UPDATE schedule SET postings = :p WHERE id = :id"),
                {"p": p, "id": row_id},
            )
        for col in ("amount", "currency", "from_account", "to_account"):
            if col in sched_cols:
                conn.execute(text(f"ALTER TABLE schedule DROP COLUMN {col}"))


def _migrate_occurrence(engine) -> None:
    occ_cols = _columns(engine, "occurrence")

    # Validation pass: read all rows with non-NULL override_amount and resolve
    # each to the first posting id before any DDL.
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, schedule_id, override_amount FROM occurrence"
        )).all()

        updates: list[tuple[str, int]] = []  # (json_str, occ_id)
        for r in rows:
            data: dict[str, str] = {}
            if r.override_amount is not None:
                sch = conn.execute(
                    text("SELECT postings FROM schedule WHERE id = :sid"),
                    {"sid": r.schedule_id},
                ).first()
                raw = sch.postings if sch else None
                if raw is None:
                    reason = "schedule not found" if sch is None else "schedule postings empty"
                    raise ValueError(
                        f"occurrence id={r.id}: override_amount={r.override_amount} cannot be migrated; "
                        f"{reason}. Remove the override or restore the schedule before upgrading."
                    )
                try:
                    postings = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"occurrence id={r.id}, schedule id={r.schedule_id}: "
                        f"postings column contains malformed JSON — {exc}. "
                        "Fix the schedule before upgrading."
                    ) from exc
                if not postings:
                    raise ValueError(
                        f"occurrence id={r.id}: override_amount={r.override_amount} cannot be migrated; "
                        "schedule postings empty. Remove the override or restore the schedule before upgrading."
                    )
                try:
                    first_id = postings[0]["id"]
                except (KeyError, TypeError) as exc:
                    raise ValueError(
                        f"occurrence id={r.id}, schedule id={r.schedule_id}: "
                        f"first posting is missing an 'id' field — {exc}. "
                        "Fix the schedule before upgrading."
                    ) from exc
                data[first_id] = _dec_str(r.override_amount)
            updates.append((json.dumps(data), r.id))

    # All rows validated — now mutate the schema.
    with engine.begin() as conn:
        if "override_amounts" not in occ_cols:
            conn.execute(text("ALTER TABLE occurrence ADD COLUMN override_amounts JSON"))
        for d, occ_id in updates:
            conn.execute(
                text("UPDATE occurrence SET override_amounts = :d WHERE id = :id"),
                {"d": d, "id": occ_id},
            )
        if "override_amount" in occ_cols:
            conn.execute(text("ALTER TABLE occurrence DROP COLUMN override_amount"))


def _add_target_file_column(engine) -> None:
    sched_cols = _columns(engine, "schedule")
    if sched_cols and "target_file" not in sched_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE schedule ADD COLUMN target_file VARCHAR"))


def migrate_legacy_schema(engine) -> None:
    """Idempotently upgrade a pre-multi-posting database. No-op on fresh or
    already-migrated databases. Schedule is migrated before occurrence because
    the occurrence backfill reads the schedule's new posting ids.

    Guard condition is OLD column presence, not absence of new column, so a
    half-migrated DB (new column added but old not yet dropped) resumes cleanly.
    Newer columns (e.g. schedule.target_file) are added idempotently in a
    separate step that runs unconditionally on every startup."""
    sched_cols = _columns(engine, "schedule")
    if sched_cols and "from_account" in sched_cols:
        _migrate_schedule(engine)
    occ_cols = _columns(engine, "occurrence")
    if occ_cols and "override_amount" in occ_cols:
        _migrate_occurrence(engine)
    _add_target_file_column(engine)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    migrate_legacy_schema(engine)
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
