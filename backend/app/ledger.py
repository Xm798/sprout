import os
import tempfile

from beancount import loader
from beancount.core import data

# The default pickle load cache invalidates only on mtimes of files already in
# the cached include list, so a file newly created under an existing glob
# include would be invisible to included_files on ledgers that load >1s.
# Deterministic loads also keep .picklecache files out of the user's ledger.
loader.initialize(use_cache=False)


class ConflictError(RuntimeError):
    """State conflict (e.g. re-adding a transaction that is still present).

    Defined here rather than in services so ledger-level lookups can raise it
    without a circular import; services re-exports it."""


def _load(path: str):
    return loader.load_file(path)


def included_files(main_path: str) -> set[str]:
    """Real paths of every file the ledger loads, including the main file.

    Uses the loader's own ``options_map["include"]`` so glob includes,
    relative paths, cycles, and missing includes are all handled by
    beancount itself — a textual walk of ``include`` directives would miss
    glob-covered files and cause duplicate includes downstream.
    """
    _entries, _errors, options_map = _load(os.path.abspath(main_path))
    return {os.path.realpath(p) for p in options_map.get("include", [])}


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


def load_sprout_ids(main_path: str) -> set[str]:
    """Set of ``sprout-id`` metadata values on transactions across the include tree.

    Raises FileNotFoundError when the main file is unset or missing so callers can
    distinguish "ledger not configured" from "id absent". Load errors do not abort
    the scan — beancount returns partial entries alongside errors.
    """
    if not main_path or not os.path.exists(main_path):
        raise FileNotFoundError(main_path or "ledger main file not configured")
    entries, _errors, _options = _load(main_path)
    ids: set[str] = set()
    for e in entries:
        if isinstance(e, data.Transaction):
            sid = e.meta.get("sprout-id")
            if sid:
                ids.add(sid)
    return ids


def find_transaction(main_path: str, sprout_id: str) -> tuple[str, int] | None:
    """Locate the transaction carrying ``sprout-id == sprout_id``.

    Returns the loader-reported ``(filename, lineno)`` — absolute path and
    1-based header line, correct across includes — or None when the id is
    absent from the include tree. Raises FileNotFoundError like
    ``load_sprout_ids`` when the main file is unset or missing, and
    ConflictError when the id appears more than once.
    """
    located, _errors = find_transaction_with_errors(main_path, sprout_id)
    return located


def find_transaction_with_errors(
    main_path: str, sprout_id: str
) -> tuple[tuple[str, int] | None, list[str]]:
    """``find_transaction`` plus the load's error messages, so unconfirm can
    reuse the locate load as its pre-delete baseline (two loads total)."""
    if not main_path or not os.path.exists(main_path):
        raise FileNotFoundError(main_path or "ledger main file not configured")
    entries, errors, _options = _load(os.path.abspath(main_path))
    matches = [
        (e.meta["filename"], e.meta["lineno"])
        for e in entries
        if isinstance(e, data.Transaction) and e.meta.get("sprout-id") == sprout_id
    ]
    if len(matches) > 1:
        raise ConflictError(
            f'sprout-id "{sprout_id}" appears {len(matches)} times in the ledger; '
            "inspect and resolve the duplicates manually (a plugin that clones "
            "entries can also cause this)"
        )
    return (matches[0] if matches else None), _error_messages(errors)


def new_load_errors(main_path: str, baseline: list[str]) -> list[str]:
    """Error messages from loading the ledger now that are absent from
    ``baseline`` — same multiset diff as ``validate_snippet``."""
    _e, errors, _o = _load(os.path.abspath(main_path))
    return _diff_messages(baseline, _error_messages(errors))


def _error_messages(errors) -> list[str]:
    return [getattr(e, "message", str(e)) for e in errors]


def _diff_messages(base_msgs: list[str], new_msgs: list[str]) -> list[str]:
    """Messages in `new_msgs` not accounted for by `base_msgs` (multiset)."""
    remaining: dict[str, int] = {}
    for m in base_msgs:
        remaining[m] = remaining.get(m, 0) + 1
    new: list[str] = []
    for m in new_msgs:
        if remaining.get(m, 0) > 0:
            remaining[m] -= 1
        else:
            new.append(m)
    return new


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
    return _diff_messages(base_msgs, _error_messages(comb_errors))
