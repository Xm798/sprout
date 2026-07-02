import datetime
import logging
import zoneinfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session

from app.config import AppConfig
from app.db import engine
from app.notify.reminders import run_due_reminders, enabled_channels

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
POLL_MINUTES = 15


def _now_in_tz(tz: str) -> datetime.datetime:
    zone = zoneinfo.ZoneInfo(tz) if tz else None
    return datetime.datetime.now(zone)


def should_run_now(cfg: AppConfig, now: datetime.datetime | None = None) -> bool:
    """True when reminders are enabled, at least one channel is on, and the
    current wall-clock time in the configured tz is at/after notify_time."""
    if not cfg.notify_enabled or not enabled_channels(cfg):
        return False
    try:
        if now is None:
            now = _now_in_tz(cfg.notify_timezone)
        elif cfg.notify_timezone:
            now = now.astimezone(zoneinfo.ZoneInfo(cfg.notify_timezone))
        hh, mm = (int(x) for x in cfg.notify_time.split(":"))
    except Exception:
        logger.warning("invalid notify config (time=%r tz=%r)",
                       cfg.notify_time, cfg.notify_timezone)
        return False
    return (now.hour, now.minute) >= (hh, mm)


def notification_tick() -> None:
    """Plain sync job — APScheduler runs it in a thread pool, so the blocking
    Apprise sends and the sync Session never touch the event loop."""
    try:
        with Session(engine) as session:
            cfg = session.get(AppConfig, 1)
            if cfg is None:
                return
            now = _now_in_tz(cfg.notify_timezone)
            if not should_run_now(cfg, now):
                return
            run_due_reminders(session, cfg, now)
    except Exception:
        logger.exception("notification tick failed")


def start() -> None:
    if scheduler.running:
        return
    scheduler.add_job(notification_tick, IntervalTrigger(minutes=POLL_MINUTES),
                      id="due_reminders", max_instances=1, coalesce=True,
                      replace_existing=True)
    scheduler.start()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
