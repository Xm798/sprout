from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.config import AppConfig
from app.ledger import load_accounts, load_currencies

router = APIRouter()


def _config(session: Session) -> AppConfig:
    cfg = session.get(AppConfig, 1)
    if cfg is None:
        raise HTTPException(500, "config not initialized")
    return cfg


@router.get("/accounts")
def accounts(session: Session = Depends(get_session)) -> list[str]:
    return load_accounts(_config(session).ledger_main_file)


@router.get("/currencies")
def currencies(session: Session = Depends(get_session)) -> list[str]:
    return load_currencies(_config(session).ledger_main_file)


@router.get("/config", response_model=AppConfig)
def get_config(session: Session = Depends(get_session)) -> AppConfig:
    return _config(session)


@router.put("/config", response_model=AppConfig)
def update_config(payload: AppConfig, session: Session = Depends(get_session)) -> AppConfig:
    cfg = _config(session)
    data = payload.model_dump(exclude={"id"})
    for key, value in data.items():
        setattr(cfg, key, value)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg
