import os
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_scheduler_not_started_when_env_disabled(monkeypatch):
    monkeypatch.setenv("SPROUT_ENABLE_SCHEDULER", "0")
    import app.main as main
    with patch("app.notify.scheduler.start") as start, \
         patch("app.db.init_db"):
        with TestClient(main.app):     # triggers lifespan
            pass
    start.assert_not_called()


def test_scheduler_started_when_env_enabled(monkeypatch):
    monkeypatch.setenv("SPROUT_ENABLE_SCHEDULER", "1")
    import app.main as main
    with patch("app.notify.scheduler.start") as start, \
         patch("app.notify.scheduler.shutdown"), \
         patch("app.db.init_db"):
        with TestClient(main.app):
            pass
    start.assert_called_once()
