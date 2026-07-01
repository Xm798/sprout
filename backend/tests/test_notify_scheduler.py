import datetime
import zoneinfo

from app.config import AppConfig
from app.notify import scheduler as sch


def _cfg(**over):
    c = AppConfig(id=1, notify_enabled=True, notify_time="08:00",
                  notify_channels=[{"name": "ios", "url": "bark://h/k", "enabled": True}])
    for k, v in over.items():
        setattr(c, k, v)
    return c


def test_should_run_only_after_configured_time():
    cfg = _cfg(notify_timezone="UTC")
    assert sch.should_run_now(cfg, datetime.datetime(2026, 6, 8, 7, 59, tzinfo=zoneinfo.ZoneInfo("UTC"))) is False
    assert sch.should_run_now(cfg, datetime.datetime(2026, 6, 8, 8, 1, tzinfo=zoneinfo.ZoneInfo("UTC"))) is True


def test_disabled_or_no_channels_never_runs():
    assert sch.should_run_now(_cfg(notify_enabled=False, notify_timezone="UTC"),
                              datetime.datetime(2026, 6, 8, 12, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))) is False
    assert sch.should_run_now(_cfg(notify_channels=[], notify_timezone="UTC"),
                              datetime.datetime(2026, 6, 8, 12, 0, tzinfo=zoneinfo.ZoneInfo("UTC"))) is False


def test_invalid_timezone_is_safe():
    # A bad tz must not raise out of should_run_now.
    assert sch.should_run_now(_cfg(notify_timezone="Not/AZone"),
                              datetime.datetime(2026, 6, 8, 12, 0)) is False


def test_notification_tick_passes_tz_aware_datetime():
    """notification_tick must pass a tz-aware datetime (in the configured tz) to
    run_due_reminders — not a naive datetime.now()."""
    from unittest.mock import patch, MagicMock

    tz = "America/New_York"
    cfg = _cfg(notify_timezone=tz)
    received = []

    def fake_run(session, c, now):
        received.append(now)
        return 0

    mock_sess = MagicMock()
    mock_sess.__enter__ = MagicMock(return_value=mock_sess)
    mock_sess.__exit__ = MagicMock(return_value=False)
    mock_sess.get = MagicMock(return_value=cfg)

    with patch("app.notify.scheduler.Session", return_value=mock_sess), \
         patch("app.notify.scheduler.should_run_now", return_value=True), \
         patch("app.notify.scheduler.run_due_reminders", side_effect=fake_run):
        sch.notification_tick()

    assert received, "run_due_reminders was not called"
    assert received[0].tzinfo is not None, "datetime must be tz-aware"
    assert str(received[0].tzinfo) == tz
