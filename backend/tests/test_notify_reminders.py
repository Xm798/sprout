import datetime
from unittest.mock import patch

from sqlmodel import select

from app.models import Schedule, Occurrence, NotificationLog
from app.notify import reminders


def _setup(session, config, lead=3):
    config.notify_enabled = True
    config.notify_lead_days = lead
    config.notify_channels = [
        {"name": "ios", "url": "bark://h/k", "enabled": True},
        {"name": "off", "url": "tgram://t/c", "enabled": False},
    ]
    session.add(Schedule(name="rent", interval_unit="month", interval_count=1,
                         anchor_date=datetime.date(2026, 6, 9), status="active",
                         postings=[{"id": "m", "account": "Ex", "amount": "100.00",
                                    "currency": "USD", "cost": None, "price": None}]))
    session.commit()


def test_sends_to_enabled_channels_within_window_and_logs(session, config):
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)   # 6/9 occurrence is within 3-day lead
    with patch("app.notify.reminders.send_to_channels",
               return_value={"ios": True}) as send:
        n = reminders.run_due_reminders(session, config, now)
    assert n == 1
    send.assert_called_once()                          # only the enabled channel
    assert [c["name"] for c in send.call_args.args[0]] == ["ios"]
    logs = session.exec(select(NotificationLog)).all()
    assert len(logs) == 1 and logs[0].channel_name == "ios"


def test_dedup_does_not_resend_logged_channel(session, config):
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}):
        reminders.run_due_reminders(session, config, now)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}) as send2:
        n2 = reminders.run_due_reminders(session, config, now)
    assert n2 == 0
    send2.assert_not_called()


def test_failed_channel_not_logged_and_retried(session, config):
    config.notify_enabled = True
    config.notify_lead_days = 3
    config.notify_channels = [{"name": "ios", "url": "bark://h/k", "enabled": True}]
    session.add(Schedule(name="rent", interval_unit="month", interval_count=1,
                         anchor_date=datetime.date(2026, 6, 9), status="active", postings=[]))
    session.commit()
    now = datetime.datetime(2026, 6, 8, 9, 0)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": "err"}):
        reminders.run_due_reminders(session, config, now)
    assert session.exec(select(NotificationLog)).all() == []   # failure: no log row
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}) as retry:
        n = reminders.run_due_reminders(session, config, now)
    assert n == 1
    retry.assert_called_once()                                  # retried next run
