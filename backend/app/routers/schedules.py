import datetime
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.bean_parse import ParseError, ParsedTransaction, parse_transaction
from app.config import AppConfig
from app.db import get_session, get_config
from app.loan import DegenerateLoan
from app.models import Occurrence, Schedule, ScheduleBase, ScheduleCreate, ScheduleRead
from app.postings import parse_postings, validate_postings, headline, dump_postings
from app.writer import validate_target_file
from app import services

router = APIRouter(prefix="/schedules")


class ParseRequest(BaseModel):
    text: str


def _read(sch: Schedule) -> ScheduleRead:
    postings = parse_postings(sch.postings)
    if sch.kind == "loan":
        amount, currency = services.loan_headline(sch)
    else:
        amount, currency = headline(postings)
    base = {f: getattr(sch, f) for f in ScheduleBase.model_fields}
    return ScheduleRead(
        **base, id=sch.id, postings=postings,
        kind=sch.kind, loan=sch.loan, events=sch.events or [],
        headline_amount=amount, headline_currency=currency,
        created_at=sch.created_at, updated_at=sch.updated_at,
    )


def _validate_or_422(payload: ScheduleCreate, config: AppConfig) -> None:
    if payload.kind == "loan":
        errors = services.validate_loan(payload)
    else:
        errors = validate_postings(payload.postings)
    if errors:
        raise HTTPException(422, "; ".join(errors))
    try:
        payload.target_file = validate_target_file(config, payload.target_file)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("", response_model=ScheduleRead)
def create(payload: ScheduleCreate, session: Session = Depends(get_session)) -> ScheduleRead:
    _validate_or_422(payload, get_config(session))
    sch = Schedule(**payload.model_dump(exclude={"postings"}), postings=dump_postings(payload.postings))
    session.add(sch)
    session.commit()
    session.refresh(sch)
    return _read(sch)


@router.get("", response_model=list[ScheduleRead])
def list_all(session: Session = Depends(get_session)) -> list[ScheduleRead]:
    return [_read(s) for s in session.exec(select(Schedule)).all()]


# Registered before the /{schedule_id} routes so the literal "parse" always wins.
@router.post("/parse", response_model=ParsedTransaction)
def parse(payload: ParseRequest) -> ParsedTransaction:
    try:
        return parse_transaction(payload.text)
    except ParseError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{schedule_id}", response_model=ScheduleRead)
def get_one(schedule_id: int, session: Session = Depends(get_session)) -> ScheduleRead:
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise HTTPException(404, "schedule not found")
    return _read(sch)


@router.put("/{schedule_id}", response_model=ScheduleRead)
def update(schedule_id: int, payload: ScheduleCreate, session: Session = Depends(get_session)) -> ScheduleRead:
    config = get_config(session)
    _validate_or_422(payload, config)
    if services.loan_terms_locked(session, schedule_id, payload):
        raise HTTPException(422, "loan terms are locked once an occurrence is confirmed")
    try:
        sch = services.update_schedule(
            session, config, schedule_id, payload, datetime.date.today()
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return _read(sch)


@router.delete("/{schedule_id}")
def delete(schedule_id: int, session: Session = Depends(get_session)) -> dict:
    try:
        services.delete_schedule(session, schedule_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    return {"ok": True}


class EventBody(BaseModel):
    id: Optional[str] = None
    kind: str
    date: datetime.date
    amount: Optional[Decimal] = None     # prepayment
    mode: Optional[str] = None           # prepayment: shorten_term | reduce_payment
    annual_rate: Optional[Decimal] = None  # rate_change


def _get_freeze_boundary(session: Session, schedule_id: int) -> Optional[datetime.date]:
    """Return the last confirmed occurrence's due_date for this schedule, or None."""
    confirmed = session.exec(
        select(Occurrence).where(
            Occurrence.schedule_id == schedule_id,
            Occurrence.status == "confirmed",
        )
    ).all()
    return max(occ.due_date for occ in confirmed) if confirmed else None


@router.post("/{schedule_id}/events", response_model=ScheduleRead)
def add_event(
    schedule_id: int, body: EventBody, session: Session = Depends(get_session)
) -> ScheduleRead:
    config = get_config(session)
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise HTTPException(404, "schedule not found")
    if sch.kind != "loan":
        raise HTTPException(422, "events are only supported for loan schedules")

    # Payment dates are regular (non-prepayment) due dates in the current table.
    table = services._loan_table(sch)
    payment_dates = {row.due_date for row in table if not row.is_prepayment}
    if body.date not in payment_dates:
        raise HTTPException(422, f"event date {body.date} is not a scheduled payment date")

    # Freeze boundary: event must land strictly after the last confirmed occurrence.
    freeze_boundary = _get_freeze_boundary(session, schedule_id)
    if freeze_boundary is not None and body.date <= freeze_boundary:
        raise HTTPException(
            422,
            f"event date {body.date} must be strictly after the last confirmed "
            f"installment ({freeze_boundary})",
        )

    event_id = body.id or uuid.uuid4().hex
    event_dict: dict = {"id": event_id, "kind": body.kind, "date": body.date.isoformat()}
    if body.amount is not None:
        event_dict["amount"] = str(body.amount)
    if body.mode is not None:
        event_dict["mode"] = body.mode
    if body.annual_rate is not None:
        event_dict["annual_rate"] = str(body.annual_rate)

    sch.events = [*sch.events, event_dict]
    sch.updated_at = datetime.datetime.now()
    try:
        services.reconcile_loan_pending(session, config, sch, datetime.date.today())
    except (DegenerateLoan, ValueError) as exc:
        raise HTTPException(422, str(exc))
    session.add(sch)
    session.commit()
    session.refresh(sch)
    return _read(sch)


@router.delete("/{schedule_id}/events/{event_id}", response_model=ScheduleRead)
def delete_event(
    schedule_id: int, event_id: str, session: Session = Depends(get_session)
) -> ScheduleRead:
    config = get_config(session)
    sch = session.get(Schedule, schedule_id)
    if sch is None:
        raise HTTPException(404, "schedule not found")
    if sch.kind != "loan":
        raise HTTPException(422, "events are only supported for loan schedules")

    # Find the target event first — needed for the freeze-boundary check.
    target = next((e for e in (sch.events or []) if e.get("id") == event_id), None)
    if target is None:
        raise HTTPException(404, f"event {event_id!r} not found on this schedule")

    event_date = datetime.date.fromisoformat(target["date"])
    freeze_boundary = _get_freeze_boundary(session, schedule_id)
    if freeze_boundary is not None and event_date <= freeze_boundary:
        raise HTTPException(
            422,
            f"event {event_id!r} is on {event_date}, at or before the last confirmed "
            f"installment ({freeze_boundary}); frozen events cannot be removed",
        )

    remaining = [e for e in (sch.events or []) if e.get("id") != event_id]
    sch.events = remaining
    sch.updated_at = datetime.datetime.now()
    try:
        services.reconcile_loan_pending(session, config, sch, datetime.date.today())
    except (DegenerateLoan, ValueError) as exc:
        raise HTTPException(422, str(exc))
    session.add(sch)
    session.commit()
    session.refresh(sch)
    return _read(sch)
