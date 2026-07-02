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
from app.notify.reminders import enabled_channels
from app.writer import resolve_root

MASK = "••••"
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


class TestBody(BaseModel):
    channel_name: str | None = None


def _masked(cfg: AppConfig) -> dict:
    chans = [{"id": c.get("id", ""), "name": c["name"], "url": MASK if c.get("url") else "",
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
    return _masked(_config(session))


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
    existing: dict[str, str] = {}
    existing_by_id: dict[str, str] = {}
    # F6: build id- and name-keyed lookups so a rename (new name, masked URL, same id) resolves correctly
    for c in (cfg.notify_channels or []):
        existing[c["name"]] = c.get("url", "")
        if c.get("id"):
            existing_by_id[c["id"]] = c.get("url", "")
    resolved: list[dict] = []
    for ch in payload.notify_channels:
        if not ch.name:
            raise HTTPException(422, "channel name required")
        if ch.url == MASK:
            # Prefer id-based lookup; fall back to name lookup for older payloads without an id
            url = existing_by_id.get(ch.id, "") or existing.get(ch.name, "")
        else:
            url = ch.url
        if not url:
            raise HTTPException(422, f"channel {ch.name} needs a URL")
        chan_id = ch.id or uuid.uuid4().hex
        resolved.append({"id": chan_id, "name": ch.name, "url": url, "enabled": ch.enabled})

    cfg.notify_enabled = payload.notify_enabled
    cfg.notify_lead_days = payload.notify_lead_days
    cfg.notify_time = payload.notify_time
    cfg.notify_timezone = payload.notify_timezone
    cfg.notify_channels = resolved
    session.add(cfg)
    session.commit()
    return _masked(cfg)


@router.post("/config/notifications/test")
def test_notifications(body: TestBody, session: Session = Depends(get_session)) -> dict:
    cfg = _config(session)
    # F7: None means "test all"; any explicit string (even "") means "test just this one"
    if body.channel_name is not None:
        chans = [c for c in (cfg.notify_channels or []) if c.get("url") and c["name"] == body.channel_name]
    else:
        chans = enabled_channels(cfg)
    if not chans:
        raise HTTPException(404, "no matching channel")
    return send_to_channels(chans, "Sprout test", "Notifications are working ✅")
