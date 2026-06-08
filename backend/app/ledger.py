import os
import tempfile

from beancount import loader
from beancount.core import data


def _load(path: str):
    return loader.load_file(path)


def load_accounts(path: str) -> list[str]:
    entries, _errors, _options = _load(path)
    accounts = {e.account for e in entries if isinstance(e, data.Open)}
    return sorted(accounts)


def load_currencies(path: str) -> list[str]:
    _entries, _errors, options_map = _load(path)
    return list(options_map.get("operating_currency", []))
