import logging

import apprise

logger = logging.getLogger(__name__)


def send_to_channels(channels: list[dict], title: str, body: str) -> dict[str, object]:
    """Send (title, body) to each channel independently.

    Each channel gets its own single-URL Apprise instance so the boolean result
    maps 1:1 to that channel (a batched notify() only returns an aggregate bool).
    Returns {channel_name: True | False | "<error string>"}.
    """
    results: dict[str, object] = {}
    for ch in channels:
        name = ch.get("name") or ch.get("url", "")
        try:
            ap = apprise.Apprise()
            if not ap.add(ch["url"]):
                results[name] = "invalid URL"
                continue
            results[name] = bool(ap.notify(title=title, body=body))
        except Exception as exc:  # one channel's failure never affects the others
            logger.warning("notify channel %s failed: %s", name, exc)
            results[name] = str(exc)
    return results
