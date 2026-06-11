from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.config import AppConfig
from app.models import Occurrence
from app import services

router = APIRouter(prefix="/history")


def _config(session: Session) -> AppConfig:
    cfg = session.get(AppConfig, 1)
    if cfg is None:
        raise HTTPException(500, "config not initialized")
    return cfg


@router.get("", response_model=list[Occurrence])
def history(session: Session = Depends(get_session)) -> list[Occurrence]:
    return services.list_history(session)


@router.get("/check")
def check(session: Session = Depends(get_session)) -> dict:
    cfg = _config(session)
    try:
        return {"missing": services.find_missing_occurrences(session, cfg)}
    except FileNotFoundError as exc:
        raise HTTPException(422, f"ledger main file not found: {exc}")


@router.post("/{occurrence_id}/readd", response_model=Occurrence)
def readd(occurrence_id: int, session: Session = Depends(get_session)) -> Occurrence:
    cfg = _config(session)
    try:
        return services.readd_occurrence(session, cfg, occurrence_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except services.ConflictError as exc:
        raise HTTPException(409, str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(422, f"ledger main file not found: {exc}")
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc))


@router.get("/{occurrence_id}/written")
def written(occurrence_id: int, session: Session = Depends(get_session)) -> dict:
    cfg = _config(session)
    try:
        path, text = services.get_written_transaction(session, cfg, occurrence_id)
        return {"path": path, "text": text}
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except services.ConflictError as exc:
        raise HTTPException(409, str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(422, f"ledger main file not found: {exc}")
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/{occurrence_id}/unconfirm", response_model=Occurrence)
def unconfirm(occurrence_id: int, session: Session = Depends(get_session)) -> Occurrence:
    cfg = _config(session)
    try:
        return services.unconfirm_occurrence(session, cfg, occurrence_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except services.ConflictError as exc:
        raise HTTPException(409, str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(422, f"ledger main file not found: {exc}")
    except (ValueError, ArithmeticError) as exc:
        raise HTTPException(422, str(exc))


@router.post("/{occurrence_id}/unskip", response_model=Occurrence)
def unskip(occurrence_id: int, session: Session = Depends(get_session)) -> Occurrence:
    try:
        return services.unskip_occurrence(session, occurrence_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except services.ConflictError as exc:
        raise HTTPException(409, str(exc))
