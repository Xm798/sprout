import json
import os
import uuid
from decimal import Decimal

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
    """Canonical fixed-point string with >=2 decimals (matches bean_format render,
    so a legacy `15` and a legacy Decimal('15.00000000') both store as '15.00')."""
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
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE schedule ADD COLUMN postings JSON"))
        rows = conn.execute(text(
            "SELECT id, amount, currency, from_account, to_account FROM schedule"
        )).all()
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
            conn.execute(
                text("UPDATE schedule SET postings = :p WHERE id = :id"),
                {"p": json.dumps(postings), "id": r.id},
            )
        for col in ("amount", "currency", "from_account", "to_account"):
            conn.execute(text(f"ALTER TABLE schedule DROP COLUMN {col}"))


def _migrate_occurrence(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE occurrence ADD COLUMN override_amounts JSON"))
        rows = conn.execute(text(
            "SELECT id, schedule_id, override_amount FROM occurrence"
        )).all()
        for r in rows:
            data: dict[str, str] = {}
            if r.override_amount is not None:
                sch = conn.execute(
                    text("SELECT postings FROM schedule WHERE id = :sid"),
                    {"sid": r.schedule_id},
                ).first()
                raw = sch.postings if sch else None
                postings = json.loads(raw) if isinstance(raw, str) else (raw or [])
                if postings:
                    data[postings[0]["id"]] = _dec_str(r.override_amount)
                else:
                    reason = "schedule not found" if sch is None else "schedule postings empty"
                    raise RuntimeError(
                        f"occurrence id={r.id}: override_amount={r.override_amount} cannot be migrated; "
                        f"{reason}. Remove the override or restore the schedule before upgrading."
                    )
            conn.execute(
                text("UPDATE occurrence SET override_amounts = :d WHERE id = :id"),
                {"d": json.dumps(data), "id": r.id},
            )
        conn.execute(text("ALTER TABLE occurrence DROP COLUMN override_amount"))


def migrate_legacy_schema(engine) -> None:
    """Idempotently upgrade a pre-multi-posting database. No-op on fresh or
    already-migrated databases. Schedule is migrated before occurrence because
    the occurrence backfill reads the schedule's new posting ids."""
    sched_cols = _columns(engine, "schedule")
    if sched_cols and "postings" not in sched_cols and "from_account" in sched_cols:
        _migrate_schedule(engine)
    occ_cols = _columns(engine, "occurrence")
    if occ_cols and "override_amounts" not in occ_cols and "override_amount" in occ_cols:
        _migrate_occurrence(engine)


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
