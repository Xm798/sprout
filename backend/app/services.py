import datetime
from typing import Optional

from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Schedule, Occurrence, ScheduleCreate
from app.due_engine import compute_due_dates
from app.bean_format import format_transaction
from app.postings import Posting, parse_postings, dump_postings, validate_postings, validate_overrides, struct_key
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


def _effective_meta(
    occ: Occurrence, sch: Schedule, *,
    override_date: Optional[datetime.date] = None,
    override_narration: Optional[str] = None,
):
    date = override_date or occ.override_date or occ.due_date
    if override_narration is not None:
        narration = override_narration
    elif occ.override_narration is not None:
        narration = occ.override_narration
    else:
        narration = sch.narration
    return date, narration


def _apply_overrides(postings: list[Posting], overrides: dict) -> list[Posting]:
    overrides = overrides or {}
    out: list[Posting] = []
    for p in postings:
        if p.id in overrides:
            p = p.model_copy(update={"amount": overrides[p.id]})
        out.append(p)
    return out


def _merged_overrides(occ: Occurrence, incoming: Optional[dict]) -> dict:
    """Merge stored override_amounts with transient incoming overrides."""
    merged = dict(occ.override_amounts or {})
    if incoming:
        merged.update(incoming)
    return merged


def _validate_effective(postings: list[Posting], merged: dict) -> list[Posting]:
    """Validate merged overrides and return effective postings, raising ValueError on errors."""
    errors = validate_overrides(postings, merged)
    effective = _apply_overrides(postings, merged)
    errors += validate_postings(effective)
    if errors:
        raise ValueError("; ".join(errors))
    return effective


def render_occurrence(
    occ: Occurrence, sch: Schedule, *,
    effective_postings: list[Posting],
    override_date: Optional[datetime.date] = None,
    override_narration: Optional[str] = None,
) -> str:
    """Pure render of an occurrence's transaction. `override_*` are transient
    (not persisted); when None, the occurrence's stored values are used.
    `effective_postings` are the pre-validated postings supplied by the caller."""
    date, narration = _effective_meta(occ, sch, override_date=override_date, override_narration=override_narration)
    tags = [t.strip() for t in sch.tags.split(",") if t.strip()]
    return format_transaction(
        date=date, payee=sch.name, narration=narration, postings=effective_postings,
        tags=tags, meta={"sprout-id": occ.sprout_id},
    )


def build_preview(session: Session, occurrence_id: int, **transient) -> str:
    occ = session.get(Occurrence, occurrence_id)
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    sch = session.get(Schedule, occ.schedule_id)
    if sch is None:
        raise LookupError(f"schedule {occ.schedule_id} not found")
    postings = parse_postings(sch.postings)
    # Validate the MERGED overrides (stored + transient), mirroring confirm:
    # stale stored keys must error too, not just incoming ones.
    merged = _merged_overrides(occ, transient.get("override_amounts"))
    effective = _validate_effective(postings, merged)
    return render_occurrence(occ, sch, effective_postings=effective, **{
        k: v for k, v in transient.items() if k != "override_amounts"
    })


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
    if sch is None:
        raise LookupError(f"schedule {occ.schedule_id} not found")

    # Validate before mutating — compute effective postings from the incoming
    # overrides merged over any stored ones, then check structural errors and
    # unknown keys.  Raise immediately so nothing is written or persisted.
    postings = parse_postings(sch.postings)
    merged_amounts = _merged_overrides(occ, override_amounts)
    effective = _validate_effective(postings, merged_amounts)

    if override_amounts:
        occ.override_amounts = merged_amounts
    if override_date is not None:
        occ.override_date = override_date
    if override_narration is not None:
        occ.override_narration = override_narration

    text = render_occurrence(occ, sch, effective_postings=effective)
    snippet_errors = validate_snippet(config.ledger_main_file, text)
    if snippet_errors:
        raise ValueError("; ".join(snippet_errors))

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


def update_schedule(session: Session, schedule_id: int, payload: ScheduleCreate) -> Schedule:
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise LookupError(f"schedule {schedule_id} not found")

    old = {p.id: struct_key(p) for p in parse_postings(sch.postings)}
    new = {p.id: struct_key(p) for p in payload.postings}

    for key, value in payload.model_dump(exclude={"postings"}).items():
        setattr(sch, key, value)
    sch.postings = dump_postings(payload.postings)
    sch.updated_at = datetime.datetime.now()

    pendings = session.exec(
        select(Occurrence).where(
            Occurrence.schedule_id == schedule_id, Occurrence.status != "confirmed"
        )
    ).all()
    for occ in pendings:
        if not occ.override_amounts:
            continue
        kept = {
            pid: amt for pid, amt in occ.override_amounts.items()
            if pid in new and new[pid] == old.get(pid)
        }
        if kept != dict(occ.override_amounts):
            occ.override_amounts = kept
            session.add(occ)

    session.add(sch)
    session.commit()
    session.refresh(sch)
    return sch


def delete_schedule(session: Session, schedule_id: int) -> None:
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise LookupError(f"schedule {schedule_id} not found")
    occs = session.exec(
        select(Occurrence).where(Occurrence.schedule_id == schedule_id)
    ).all()
    for occ in occs:
        session.delete(occ)
    session.delete(sch)
    session.commit()
