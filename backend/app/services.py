import datetime
from typing import Optional

from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Schedule, Occurrence
from app.due_engine import compute_due_dates
from app.bean_format import format_transaction
from app.postings import Posting, parse_postings, validate_postings
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


def _effective_meta(occ: Occurrence, sch: Schedule):
    date = occ.override_date or occ.due_date
    narration = occ.override_narration if occ.override_narration is not None else sch.narration
    return date, narration


def _apply_overrides(postings: list[Posting], overrides: dict) -> list[Posting]:
    overrides = overrides or {}
    out: list[Posting] = []
    for p in postings:
        if p.id in overrides:
            p = p.model_copy(update={"amount": overrides[p.id]})
        out.append(p)
    return out


def _effective_postings(occ: Occurrence, sch: Schedule, override_amounts: Optional[dict] = None) -> list[Posting]:
    amounts = dict(occ.override_amounts or {})
    if override_amounts:
        amounts.update(override_amounts)
    return _apply_overrides(parse_postings(sch.postings), amounts)


def render_occurrence(
    occ: Occurrence, sch: Schedule, *,
    override_amounts: Optional[dict] = None,
    override_date: Optional[datetime.date] = None,
    override_narration: Optional[str] = None,
) -> str:
    """Pure render of an occurrence's transaction. `override_*` are transient
    (not persisted); when None, the occurrence's stored values are used."""
    date = override_date or occ.override_date or occ.due_date
    if override_narration is not None:
        narration = override_narration
    elif occ.override_narration is not None:
        narration = occ.override_narration
    else:
        narration = sch.narration
    postings = _effective_postings(occ, sch, override_amounts)
    tags = [t for t in sch.tags.split(",") if t]
    return format_transaction(
        date=date, payee=sch.name, narration=narration, postings=postings,
        tags=tags, meta={"sprout-id": occ.sprout_id},
    )


def build_preview(session: Session, occurrence_id: int, **transient) -> str:
    occ = session.get(Occurrence, occurrence_id)
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    sch = session.get(Schedule, occ.schedule_id)
    return render_occurrence(occ, sch, **transient)


def confirm_occurrence(
    session: Session, config: AppConfig, occurrence_id: int,
    override_amounts: Optional[dict] = None,
    override_date: Optional[datetime.date] = None,
    override_narration: Optional[str] = None,
) -> Occurrence:
    occ = session.get(Occurrence, occurrence_id)
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    if occ.status == "confirmed":
        return occ
    sch = session.get(Schedule, occ.schedule_id)

    if override_amounts:
        merged = dict(occ.override_amounts or {})
        merged.update(override_amounts)
        occ.override_amounts = merged
    if override_date is not None:
        occ.override_date = override_date
    if override_narration is not None:
        occ.override_narration = override_narration

    errors = validate_postings(_effective_postings(occ, sch))
    text = render_occurrence(occ, sch)
    errors += validate_snippet(config.ledger_main_file, text)
    if errors:
        raise ValueError("; ".join(errors))

    eff_date, _narration = _effective_meta(occ, sch)
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
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    occ.status = "skipped"
    session.add(occ)
    session.commit()
    session.refresh(occ)
    return occ
