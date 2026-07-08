import re
import uuid
import zoneinfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session, get_config as _config
from app.config import AppConfig
from app.ledger import load_accounts, load_currencies
from app.notify.channels import send_to_channels
from app.writer import resolve_root

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Channel(BaseModel):
    id: str | None = None   # stable per-channel identifier; generated server-side if absent
    name: str
    url: str
    enabled: bool = True


class NotificationSettings(BaseModel):
    notify_enabled: bool
    notify_lead_days: int
    notify_time: str
    notify_timezone: str
    notify_channels: list[Channel]


class TestChannel(BaseModel):
    name: str
    url: str


class TestBody(BaseModel):
    channels: list[TestChannel] = []


def _serialize(cfg: AppConfig) -> dict:
    chans = [{"id": c.get("id", ""), "name": c["name"], "url": c.get("url", ""),
              "enabled": c.get("enabled", True)} for c in (cfg.notify_channels or [])]
    return {"notify_enabled": cfg.notify_enabled, "notify_lead_days": cfg.notify_lead_days,
            "notify_time": cfg.notify_time, "notify_timezone": cfg.notify_timezone,
            "notify_channels": chans}

router = APIRouter()


@router.get("/bean-files")
def bean_files(session: Session = Depends(get_session)) -> list[str]:
    root = resolve_root(_config(session))
    if not root.is_dir():
        return []
    return sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*.bean") if p.is_file()
    )


@router.get("/accounts")
def accounts(session: Session = Depends(get_session)) -> list[str]:
    return load_accounts(_config(session).ledger_main_file)


@router.get("/currencies")
def currencies(session: Session = Depends(get_session)) -> list[str]:
    return load_currencies(_config(session).ledger_main_file)


_NOTIFY_FIELDS = {"notify_enabled", "notify_channels", "notify_lead_days", "notify_time", "notify_timezone"}


@router.get("/config", response_model=AppConfig, response_model_exclude=_NOTIFY_FIELDS)
def get_config(session: Session = Depends(get_session)) -> AppConfig:
    return _config(session)


@router.put("/config", response_model=AppConfig, response_model_exclude=_NOTIFY_FIELDS)
def update_config(payload: AppConfig, session: Session = Depends(get_session)) -> AppConfig:
    cfg = _config(session)
    data = payload.model_dump(exclude={"id"} | _NOTIFY_FIELDS)
    for key, value in data.items():
        setattr(cfg, key, value)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return cfg


@router.get("/config/notifications")
def get_notifications(session: Session = Depends(get_session)) -> dict:
    return _serialize(_config(session))


@router.put("/config/notifications")
def put_notifications(payload: NotificationSettings,
                      session: Session = Depends(get_session)) -> dict:
    if not _TIME_RE.match(payload.notify_time):
        raise HTTPException(422, "notify_time must be HH:MM")
    if payload.notify_timezone:
        try:
            zoneinfo.ZoneInfo(payload.notify_timezone)
        except Exception:
            raise HTTPException(422, f"unknown timezone {payload.notify_timezone}")
    if payload.notify_lead_days < 0:
        raise HTTPException(422, "notify_lead_days must be >= 0")

    # F8: reject duplicate channel names in the payload
    if len(payload.notify_channels) != len({ch.name for ch in payload.notify_channels}):
        raise HTTPException(422, "channel names must be unique")

    cfg = _config(session)
    # Name -> existing id, so an id-less payload reattaches instead of minting a new id.
    id_by_name: dict[str, str] = {
        c["name"]: c["id"] for c in (cfg.notify_channels or []) if c.get("id")
    }
    resolved: list[dict] = []
    for ch in payload.notify_channels:
        if not ch.name:
            raise HTTPException(422, "channel name required")
        if not ch.url:
            raise HTTPException(422, f"channel {ch.name} needs a URL")
        # Keep the stable id: it is the reminder-dedup key, so an id-less payload
        # (hand-written client) must reattach to the existing channel by name
        # rather than mint a new identity and re-fire every pending reminder.
        chan_id = ch.id or id_by_name.get(ch.name) or uuid.uuid4().hex
        resolved.append({"id": chan_id, "name": ch.name, "url": ch.url, "enabled": ch.enabled})

    cfg.notify_enabled = payload.notify_enabled
    cfg.notify_lead_days = payload.notify_lead_days
    cfg.notify_time = payload.notify_time
    cfg.notify_timezone = payload.notify_timezone
    cfg.notify_channels = resolved
    session.add(cfg)
    session.commit()
    return _serialize(cfg)


@router.post("/config/notifications/test")
def test_notifications(body: TestBody) -> dict:
    # Test whatever the client sends, unsaved — no DB lookup. The frontend passes
    # the current form values, so a channel can be tested before it is saved.
    chans = [{"name": c.name, "url": c.url} for c in body.channels if c.url]
    if not chans:
        return {}
    return send_to_channels(chans, "Sprout test", "Notifications are working ✅")
