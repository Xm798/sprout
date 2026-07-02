from unittest.mock import patch, MagicMock

from app.notify.channels import send_to_channels


def _apprise_factory(results):
    """Return a fake apprise.Apprise class whose notify() returns queued results
    keyed by the URL added."""
    def make():
        inst = MagicMock()
        inst._url = None
        def add(url): inst._url = url; return True
        def notify(title=None, body=None):
            r = results[inst._url]
            if isinstance(r, Exception):
                raise r
            return r
        inst.add.side_effect = add
        inst.notify.side_effect = notify
        return inst
    return make


def test_per_channel_results_and_isolation():
    channels = [
        {"name": "ios", "url": "bark://h/k"},
        {"name": "tg", "url": "tgram://t/c"},
        {"name": "wecom", "url": "wecombot://key"},
    ]
    results = {"bark://h/k": True, "tgram://t/c": False,
               "wecombot://key": RuntimeError("boom")}
    with patch("app.notify.channels.apprise.Apprise", side_effect=_apprise_factory(results)):
        out = send_to_channels(channels, "t", "b")
    assert out["ios"] is True
    assert out["tg"] is False
    assert "boom" in out["wecom"]            # exception isolated, recorded as string
