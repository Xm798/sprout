import datetime
import logging

from sqlmodel import Session, select

from app.config import AppConfig
from app.models import Schedule, Occurrence, NotificationLog
from app.services import materialize_occurrences
from app.notify.channels import send_to_channels

logger = logging.getLogger(__name__)


def enabled_channels(cfg: AppConfig) -> list[dict]:
    return [c for c in (cfg.notify_channels or [])
            if c.get("enabled") and c.get("url") and c.get("name")]


def _headline(sch: Schedule) -> str:
    for p in sch.postings or []:
        if p.get("amount"):
            return f"{p['amount']} {p.get('currency') or ''}".strip()
    return ""


def _reminder_text(sch: Schedule, occ: Occurrence) -> tuple[str, str]:
    amount = _headline(sch)
    title = f"Payment due: {sch.name}"
    body = f"{sch.name} {('— ' + amount + ' ') if amount else ''}due {occ.due_date:%Y-%m-%d}"
    return title, body


def run_due_reminders(session: Session, cfg: AppConfig, now: datetime.datetime) -> int:
    """Materialize within the lead window, then send one reminder per
    (occurrence, enabled channel) that has no NotificationLog row yet."""
    chans = enabled_channels(cfg)
    if not chans:
        return 0
    today = now.date()
    horizon = today + datetime.timedelta(days=cfg.notify_lead_days)
    materialize_occurrences(session, cfg, today, horizon=horizon)

    due = session.exec(
        select(Occurrence).where(
            Occurrence.status == "pending", Occurrence.due_date <= horizon
        )
    ).all()

    occ_ids = [o.id for o in due]
    already_by_occ: dict[int, set[str]] = {}
    if occ_ids:
        for nl in session.exec(
            select(NotificationLog).where(NotificationLog.occurrence_id.in_(occ_ids))
        ).all():
            already_by_occ.setdefault(nl.occurrence_id, set()).add(nl.channel_name)

    sch_by_id = {s.id: s for s in session.exec(
        select(Schedule).where(Schedule.id.in_({o.schedule_id for o in due}))
    ).all()} if due else {}

    sent = 0
    for occ in due:
        try:
            already = already_by_occ.get(occ.id, set())
            pending = [c for c in chans if c["name"] not in already]
            if not pending:
                continue
            sch = sch_by_id.get(occ.schedule_id)
            if sch is None:
                continue
            title, body = _reminder_text(sch, occ)
            results = send_to_channels(pending, title, body)
            for name, ok in results.items():
                if ok is True:
                    session.add(NotificationLog(occurrence_id=occ.id, channel_name=name))
                    sent += 1
            session.commit()
        except Exception:                       # one bad occurrence never aborts the batch
            logger.exception("reminder failed for occurrence %s", occ.id)
            session.rollback()
    return sent
