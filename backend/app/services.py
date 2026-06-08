import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Schedule, Occurrence
from app.due_engine import compute_due_dates
from app.bean_format import format_transaction
from app.ledger import validate_snippet
from app.writer import target_path, append_transaction


def materialize_occurrences(session: Session, config: AppConfig, today: datetime.date) -> int:
    horizon = today + datetime.timedelta(days=config.lookahead_days)
    created = 0
    schedules = session.exec(select(Schedule).where(Schedule.status == "active")).all()
    for sch in schedules:
        dates = compute_due_dates(
            sch.anchor_date, sch.interval_unit, sch.interval_count,
            horizon, sch.end_date, sch.max_count,
        )
        for d in dates:
            exists = session.exec(
                select(Occurrence).where(
                    Occurrence.schedule_id == sch.id, Occurrence.due_date == d
                )
            ).first()
            if exists:
                continue
            session.add(Occurrence(
                schedule_id=sch.id, due_date=d, status="pending",
                sprout_id=f"sch{sch.id}-{d:%Y%m%d}",
            ))
            created += 1
    session.commit()
    return created


def _effective(occ: Occurrence, sch: Schedule):
    amount = occ.override_amount if occ.override_amount is not None else sch.amount
    date = occ.override_date or occ.due_date
    narration = occ.override_narration if occ.override_narration is not None else sch.narration
    return amount, date, narration


def build_preview(session: Session, config: AppConfig, occurrence_id: int) -> str:
    occ = session.get(Occurrence, occurrence_id)
    sch = session.get(Schedule, occ.schedule_id)
    amount, date, narration = _effective(occ, sch)
    tags = [t for t in sch.tags.split(",") if t]
    postings = [
        (sch.to_account, amount, sch.currency),
        (sch.from_account, None, None),
    ]
    return format_transaction(
        date=date, payee=sch.name, narration=narration, postings=postings,
        tags=tags, meta={"sprout-id": occ.sprout_id},
    )


def confirm_occurrence(
    session: Session, config: AppConfig, occurrence_id: int,
    override_amount: Optional[Decimal] = None,
    override_date: Optional[datetime.date] = None,
    override_narration: Optional[str] = None,
) -> Occurrence:
    occ = session.get(Occurrence, occurrence_id)
    if occ.status == "confirmed":
        return occ
    if override_amount is not None:
        occ.override_amount = override_amount
    if override_date is not None:
        occ.override_date = override_date
    if override_narration is not None:
        occ.override_narration = override_narration

    text = build_preview(session, config, occurrence_id)
    errors = validate_snippet(config.ledger_main_file, text)
    if errors:
        raise ValueError("; ".join(errors))

    sch = session.get(Schedule, occ.schedule_id)
    _amount, eff_date, _narration = _effective(occ, sch)
    path = target_path(config, eff_date)
    append_transaction(path, text)

    occ.status = "confirmed"
    occ.written_path = str(path)
    occ.confirmed_at = datetime.datetime.now()
    session.add(occ)
    session.commit()
    session.refresh(occ)
    return occ


def skip_occurrence(session: Session, occurrence_id: int) -> Occurrence:
    occ = session.get(Occurrence, occurrence_id)
    occ.status = "skipped"
    session.add(occ)
    session.commit()
    session.refresh(occ)
    return occ
