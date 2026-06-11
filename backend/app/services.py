import datetime
import logging
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Schedule, Occurrence, ScheduleCreate
from app.due_engine import compute_due_dates
from app.bean_format import format_transaction, apply_beanfmt
from app.postings import Posting, parse_postings, dump_postings, validate_postings, validate_overrides, struct_key
from app.ledger import (
    ConflictError,  # noqa: F401  re-exported; routers reference services.ConflictError
    find_transaction,
    find_transaction_with_errors,
    load_sprout_ids,
    new_load_errors,
    validate_snippet,
)
from app.writer import (
    target_path, append_transaction, ensure_included, validate_target_file,
    resolve_root, read_block, delete_block, replace_file,
)

logger = logging.getLogger(__name__)


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


def _ledger_workspace(config: AppConfig) -> Optional[Path]:
    """Directory beanfmt config discovery starts from — the same root all
    writes resolve against. None when no ledger is configured."""
    if config.ledger_root or config.ledger_main_file:
        return resolve_root(config)
    return None


def render_formatted(
    occ: Occurrence, sch: Schedule, config: AppConfig, *,
    effective_postings: list[Posting], **transient,
) -> str:
    """render_occurrence plus the beanfmt pass. The formatted text is what
    gets validated and written, so every preview/write path must go through
    here rather than calling render_occurrence directly."""
    text = render_occurrence(occ, sch, effective_postings=effective_postings, **transient)
    return apply_beanfmt(text, _ledger_workspace(config))


def build_preview(session: Session, config: AppConfig, occurrence_id: int, **transient) -> str:
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
    return render_formatted(occ, sch, config, effective_postings=effective, **{
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

    # Re-validate cheaply at write time: a symlink created after the schedule
    # was saved must not let the write escape the ledger root.
    tf = validate_target_file(config, sch.target_file)

    text = render_formatted(occ, sch, config, effective_postings=effective)
    snippet_errors = validate_snippet(config.ledger_main_file, text)
    if snippet_errors:
        raise ValueError("; ".join(snippet_errors))

    eff_date, _narration = _effective_meta(occ, sch)
    path = target_path(config, eff_date, target_file=tf)
    # Same duplicate-write guard as re-add: a copy of this id surviving in the
    # target file (e.g. orphaned by a lost include, then unconfirmed as
    # "missing") must not be silently duplicated by a re-confirm. Checked
    # before ensure_included so a refused confirm leaves no side effects.
    if occ.sprout_id and path.exists() and f'sprout-id: "{occ.sprout_id}"' in path.read_text():
        raise ConflictError(
            f"transaction {occ.sprout_id} already exists in {path} — remove it "
            "or fix your include directives before confirming again"
        )
    if tf:
        ensure_included(config, path)
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


def list_history(session: Session) -> list[Occurrence]:
    """Confirmed and skipped occurrences, newest due date first. Ordering avoids
    confirmed_at, which is NULL for skipped rows and sorts differently across
    SQLite and Postgres."""
    return list(session.exec(
        select(Occurrence)
        .where(Occurrence.status != "pending")
        .order_by(Occurrence.due_date.desc(), Occurrence.id.desc())
    ).all())


def find_missing_occurrences(session: Session, config: AppConfig) -> list[int]:
    """IDs of confirmed occurrences whose sprout-id is absent from the ledger's
    include tree — i.e. written transactions a manual edit deleted or orphaned."""
    present = load_sprout_ids(config.ledger_main_file)
    confirmed = session.exec(
        select(Occurrence).where(Occurrence.status == "confirmed")
    ).all()
    return [o.id for o in confirmed if o.sprout_id and o.sprout_id not in present]


def readd_occurrence(session: Session, config: AppConfig, occurrence_id: int) -> Occurrence:
    """Re-append a confirmed occurrence whose written transaction vanished from
    the ledger. Renders from current schedule + stored overrides (the original
    text is not stored), same as confirm."""
    occ = session.get(Occurrence, occurrence_id)
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    if occ.status != "confirmed":
        raise ConflictError(f"occurrence {occurrence_id} is {occ.status}, not confirmed")
    if not occ.sprout_id:
        raise ValueError(f"occurrence {occurrence_id} has no sprout-id; cannot reconcile")
    sch = session.get(Schedule, occ.schedule_id)
    if sch is None:
        raise LookupError(f"schedule {occ.schedule_id} not found")

    if occ.sprout_id in load_sprout_ids(config.ledger_main_file):
        raise ConflictError(
            f"transaction {occ.sprout_id} is still present in the ledger"
        )

    # Same routing as confirm: honor the schedule's target_file (re-validated
    # at write time) so re-add restores into the same destination.
    tf = validate_target_file(config, sch.target_file)

    postings = parse_postings(sch.postings)
    effective = _validate_effective(postings, _merged_overrides(occ, None))
    text = render_formatted(occ, sch, config, effective_postings=effective)

    eff_date, _narration = _effective_meta(occ, sch)
    path = target_path(config, eff_date, target_file=tf)
    # The include-tree scan above cannot see files the main ledger doesn't
    # include; a direct check on the target file prevents double-appending when
    # the user's `include` line is missing.
    # Match the exact metadata line bean_format writes — a bare substring test
    # could hit comments or ids sharing a prefix (sch1- vs sch11-).
    if path.exists() and f'sprout-id: "{occ.sprout_id}"' in path.read_text():
        raise ConflictError(
            f"transaction {occ.sprout_id} already exists in {path} but is not "
            "reachable from the main ledger — check your include directives"
        )

    snippet_errors = validate_snippet(config.ledger_main_file, text)
    if snippet_errors:
        raise ValueError("; ".join(snippet_errors))
    if tf:
        ensure_included(config, path)
    append_transaction(path, text)

    occ.written_path = str(path)
    occ.confirmed_at = datetime.datetime.now()
    session.add(occ)
    session.commit()
    session.refresh(occ)
    return occ


def get_written_transaction(session: Session, config: AppConfig, occurrence_id: int) -> tuple[str, str]:
    """``(path, text)`` of a confirmed occurrence's transaction — the exact
    block as it exists in the ledger right now, including any manual edits."""
    occ = session.get(Occurrence, occurrence_id)
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    if occ.status != "confirmed":
        raise ConflictError(f"occurrence {occurrence_id} is {occ.status}, not confirmed")
    if not occ.sprout_id:
        raise ValueError(f"occurrence {occurrence_id} has no sprout-id; cannot locate it")
    located = find_transaction(config.ledger_main_file, occ.sprout_id)
    if located is None:
        raise ConflictError(f"transaction {occ.sprout_id} is not present in the ledger")
    path, lineno = located
    return path, read_block(Path(path), lineno)


def unconfirm_occurrence(session: Session, config: AppConfig, occurrence_id: int) -> Occurrence:
    """Remove a confirmed occurrence's written transaction from the ledger and
    return the occurrence to pending. The loader's filename is authoritative
    (written_path is an audit hint only); after the textual delete the ledger
    is reloaded and restored byte-identical if NEW errors appeared. When the
    transaction is already gone (reconcile's "missing" state) only the status
    reverts. Overrides and sprout_id survive so a re-confirm writes the same
    id — minus override keys stale against the current schedule postings,
    which would otherwise 422 every preview until the schedule is edited."""
    occ = session.get(Occurrence, occurrence_id)
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    if occ.status != "confirmed":
        raise ConflictError(f"occurrence {occurrence_id} is {occ.status}, not confirmed")
    sch = session.get(Schedule, occ.schedule_id)
    if sch is None:
        raise LookupError(f"schedule {occ.schedule_id} not found")

    # The locate load doubles as the pre-delete error baseline.
    located, baseline = (
        find_transaction_with_errors(config.ledger_main_file, occ.sprout_id)
        if occ.sprout_id else (None, [])
    )
    if located is not None:
        path = Path(located[0])
        snapshot = path.read_bytes()
        removed = delete_block(path, located[1])
        broke = new_load_errors(config.ledger_main_file, baseline)
        if broke:
            # Deleting can legitimately break e.g. a later balance assertion,
            # and the line surgery cannot handle every legal syntax — refuse
            # rather than leave the ledger broken.
            replace_file(path, snapshot)
            raise ValueError(
                "removing the transaction would break the ledger: " + "; ".join(broke)
            )
        # This may have been the only copy of the user's manual edits.
        logger.info(
            "unconfirm occurrence %s: removed %s from %s:\n%s",
            occurrence_id, occ.sprout_id, path, removed,
        )

    if occ.override_amounts:
        # Mirror update_schedule's stale-key pruning, which skips confirmed
        # rows: keys for postings that no longer exist must not follow the
        # occurrence back into the inbox.
        current = {p.id for p in parse_postings(sch.postings)}
        kept = {pid: amt for pid, amt in occ.override_amounts.items() if pid in current}
        if kept != dict(occ.override_amounts):
            occ.override_amounts = kept

    occ.status = "pending"
    occ.written_path = None
    occ.confirmed_at = None
    session.add(occ)
    session.commit()
    session.refresh(occ)
    return occ


def unskip_occurrence(session: Session, occurrence_id: int) -> Occurrence:
    occ = session.get(Occurrence, occurrence_id)
    if occ is None:
        raise LookupError(f"occurrence {occurrence_id} not found")
    if occ.status != "skipped":
        raise ConflictError(f"occurrence {occurrence_id} is {occ.status}, not skipped")
    occ.status = "pending"
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
