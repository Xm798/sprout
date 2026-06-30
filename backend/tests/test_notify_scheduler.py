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
