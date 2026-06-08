import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.config import AppConfig
from app.models import Occurrence
from app import services

router = APIRouter(prefix="/inbox")


class ConfirmBody(BaseModel):
    override_amount: str | None = None
    override_date: datetime.date | None = None
    override_narration: str | None = None


def _config(session: Session) -> AppConfig:
    cfg = session.get(AppConfig, 1)
    if cfg is None:
        raise HTTPException(500, "config not initialized")
    return cfg


@router.get("", response_model=list[Occurrence])
def inbox(session: Session = Depends(get_session)) -> list[Occurrence]:
    cfg = _config(session)
    services.materialize_occurrences(session, cfg, datetime.date.today())
    return session.exec(
        select(Occurrence).where(Occurrence.status == "pending").order_by(Occurrence.due_date)
    ).all()


@router.get("/{occurrence_id}/preview")
def preview(occurrence_id: int, session: Session = Depends(get_session)) -> dict:
    cfg = _config(session)
    try:
        return {"text": services.build_preview(session, cfg, occurrence_id)}
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{occurrence_id}/confirm", response_model=Occurrence)
def confirm(occurrence_id: int, body: ConfirmBody, session: Session = Depends(get_session)) -> Occurrence:
    from decimal import Decimal
    cfg = _config(session)
    try:
        return services.confirm_occurrence(
            session, cfg, occurrence_id,
            override_amount=Decimal(body.override_amount) if body.override_amount else None,
            override_date=body.override_date,
            override_narration=body.override_narration,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/{occurrence_id}/skip", response_model=Occurrence)
def skip(occurrence_id: int, session: Session = Depends(get_session)) -> Occurrence:
    try:
        return services.skip_occurrence(session, occurrence_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
