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
    """Currencies to suggest for new schedules.

    Operating currencies come first (in declared order); then any other
    commodity the ledger actually references — ``commodity`` directives,
    account ``open`` constraints, and posting units — appended alphabetically.
    """
    entries, _errors, options_map = _load(path)
    operating = list(options_map.get("operating_currency", []))
    seen = set(operating)
    extra: set[str] = set()

    def add(currency: str | None) -> None:
        if currency and currency not in seen:
            seen.add(currency)
            extra.add(currency)

    for e in entries:
        if isinstance(e, data.Commodity):
            add(e.currency)
        elif isinstance(e, data.Open) and e.currencies:
            for c in e.currencies:
                add(c)
        elif isinstance(e, data.Transaction):
            for posting in e.postings:
                units = getattr(posting, "units", None)
                if units is not None:
                    add(getattr(units, "currency", None))

    return operating + sorted(extra)


def _error_messages(errors) -> list[str]:
    return [getattr(e, "message", str(e)) for e in errors]


def validate_snippet(main_path: str, snippet: str) -> list[str]:
    """Return new error messages introduced by appending `snippet` to the ledger.

    Loads the ledger once for a baseline, then loads a temp file that includes the
    real ledger plus the snippet, and returns errors present only in the combined
    load. Empty list means the snippet parses and balances against open accounts.
    """
    abs_main = os.path.abspath(main_path)
    _e, base_errors, _o = loader.load_file(abs_main)
    base_msgs = _error_messages(base_errors)

    combined = f'include "{abs_main}"\n\n{snippet}\n'
    tmp_dir = os.path.dirname(abs_main)
    fd, tmp_path = tempfile.mkstemp(suffix=".bean", dir=tmp_dir)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(combined)
        _e2, comb_errors, _o2 = loader.load_file(tmp_path)
    finally:
        os.unlink(tmp_path)
    comb_msgs = _error_messages(comb_errors)

    remaining: dict[str, int] = {}
    for m in base_msgs:
        remaining[m] = remaining.get(m, 0) + 1
    new: list[str] = []
    for m in comb_msgs:
        if remaining.get(m, 0) > 0:
            remaining[m] -= 1
        else:
            new.append(m)
    return new
