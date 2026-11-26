import collections
from dataclasses import dataclass
import glob
import os
import re
import threading

from beancount import loader
from beancount.core import data, getters, inventory
from beancount.ops import validation
from beancount.parser import booking, options as bc_options, parser
from beancount.plugins import auto_accounts
from beancount.utils import encryption

# The default pickle load cache invalidates only on mtimes of files already in
# the cached include list, so a file newly created under an existing glob
# include would be invisible to included_files on ledgers that load >1s.
# Deterministic loads also keep .picklecache files out of the user's ledger.
loader.initialize(use_cache=False)

_INCLUDE_RE_BYTES = re.compile(rb'^\s*include\s+"([^"]+)"', re.MULTILINE)
_SNIPPET_FILENAME = "<sprout-snippet>"
_PARSER_ROOT_OPTIONS = (
    "name_assets",
    "name_liabilities",
    "name_equity",
    "name_income",
    "name_expenses",
)
_AUTO_ACCOUNTS_PLUGINS = frozenset({
    "beancount.plugins.auto_accounts",
    "beancount.plugins.auto",
})
_MAX_CACHED_LEDGERS = 8

FileSig = tuple[int, int, int]  # (st_ino, st_mtime_ns, st_size)


class ConflictError(RuntimeError):
    """State conflict (e.g. re-adding a transaction that is still present).

    Defined here rather than in services so ledger-level lookups can raise it
    without a circular import; services re-exports it."""


@dataclass
class _WatchState:
    file_sigs: dict[str, FileSig | None]
    glob_patterns: frozenset[str]
    matched_globs: frozenset[str]
    included_realpaths: frozenset[str]

    def is_fresh(self) -> bool:
        return (
            all(_file_sig(p) == sig for p, sig in self.file_sigs.items())
            and _expand_globs(self.glob_patterns) == self.matched_globs
        )

    def copy(self) -> "_WatchState":
        return _WatchState(
            file_sigs=dict(self.file_sigs),
            glob_patterns=self.glob_patterns,
            matched_globs=self.matched_globs,
            included_realpaths=self.included_realpaths,
        )


@dataclass
class _CachedLedger:
    entries: list
    errors: list
    options_map: dict
    open_close_map: dict[str, list]
    schema_bearing_files: frozenset[str]
    include_scan_cache: dict[str, tuple[FileSig, frozenset[str]]]
    full: _WatchState
    schema: _WatchState


_cache_lock = threading.RLock()
_cache: collections.OrderedDict[str, _CachedLedger] = collections.OrderedDict()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _file_sig(path: str) -> FileSig | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def _scan_file_includes(
    fpath: str,
    sig: FileSig | None,
    prev_scans: dict[str, tuple[FileSig, frozenset[str]]] | None,
) -> tuple[frozenset[str], tuple[FileSig, frozenset[str]] | None]:
    if sig is not None and prev_scans is not None:
        cached = prev_scans.get(fpath)
        if cached is not None and cached[0] == sig:
            return cached[1], cached
    try:
        with open(fpath, "rb") as f:
            raw_bytes = f.read()
    except OSError:
        return frozenset(), None
    cwd = os.path.dirname(fpath)
    found: set[str] = set()
    for match in _INCLUDE_RE_BYTES.finditer(raw_bytes):
        raw = match.group(1).decode("utf-8", errors="ignore")
        found.add(raw if os.path.isabs(raw) else os.path.join(cwd, raw))
    patterns = frozenset(found)
    entry = (sig, patterns) if sig is not None else None
    return patterns, entry


def _expand_globs(patterns: frozenset[str]) -> frozenset[str]:
    if not patterns:
        return frozenset()
    return frozenset(
        os.path.realpath(hit)
        for pat in patterns
        for hit in glob.glob(pat, recursive=True)
    )


def _build_cached_ledger(
    abs_main: str,
    prev_scans: dict[str, tuple[FileSig, frozenset[str]]] | None = None,
) -> _CachedLedger:
    entries, errors, options_map = loader.load_file(abs_main)
    real_main = os.path.realpath(abs_main)
    included_realpaths = frozenset(
        os.path.realpath(p) for p in options_map.get("include", [])
    )
    loaded_files = sorted(included_realpaths | {real_main})
    file_sigs: dict[str, FileSig | None] = {p: _file_sig(p) for p in loaded_files}

    glob_patterns: set[str] = set()
    include_scan_cache: dict[str, tuple[FileSig, frozenset[str]]] = {}
    files_with_includes: set[str] = set()
    for fpath in loaded_files:
        patterns, scan_entry = _scan_file_includes(fpath, file_sigs[fpath], prev_scans)
        if scan_entry is not None:
            include_scan_cache[fpath] = scan_entry
        if patterns:
            files_with_includes.add(fpath)
        for pat in patterns:
            if glob.has_magic(pat):
                glob_patterns.add(pat)
            else:
                real_pat = os.path.realpath(pat)
                if real_pat not in file_sigs:
                    file_sigs[real_pat] = _file_sig(real_pat)

    open_close_map = getters.get_account_open_close(entries)
    schema_bearing: set[str] = {real_main} | files_with_includes
    for entry in entries:
        if isinstance(entry, (data.Open, data.Close)):
            fname = (entry.meta or {}).get("filename")
            if fname and fname != "<load>":
                schema_bearing.add(os.path.realpath(fname))

    glob_set = frozenset(glob_patterns)
    full_state = _WatchState(
        file_sigs=file_sigs,
        glob_patterns=glob_set,
        matched_globs=_expand_globs(glob_set),
        included_realpaths=included_realpaths,
    )
    return _CachedLedger(
        entries=entries,
        errors=errors,
        options_map=options_map,
        open_close_map=open_close_map,
        schema_bearing_files=frozenset(schema_bearing),
        include_scan_cache=include_scan_cache,
        full=full_state,
        schema=full_state.copy(),
    )


def _parse_dirty_file(fpath: str, header: str):
    if not header:
        return parser.parse_file(fpath)
    with open(fpath, encoding="utf-8") as f:
        text = f.read()
    return parser.parse_string(header + text, report_filename=fpath)


def _try_advance_schema(cached: _CachedLedger) -> bool:
    """When only non-schema files changed (e.g. appended transactions), parse just
    those files to confirm no Open/Close/include/parse errors were introduced
    and advance ``cached.schema`` without a full ledger reload."""
    state = cached.schema
    new_sigs: dict[str, FileSig | None] = {}
    dirty_paths: list[str] = []

    for fpath, expected in state.file_sigs.items():
        cur = _file_sig(fpath)
        if cur != expected:
            if cur is None or fpath in cached.schema_bearing_files:
                return False
            new_sigs[fpath] = cur
            dirty_paths.append(fpath)

    cur_globs = _expand_globs(state.glob_patterns)
    if state.matched_globs - cur_globs:
        return False
    for fpath in cur_globs - state.matched_globs:
        if fpath in cached.schema_bearing_files:
            return False
        cur = _file_sig(fpath)
        if cur is None:
            return False
        new_sigs[fpath] = cur
        if fpath not in dirty_paths:
            dirty_paths.append(fpath)

    if not dirty_paths:
        return True

    header = _parser_option_header(cached.options_map)
    for fpath in dirty_paths:
        if encryption.is_encrypted_file(fpath):
            return False
        try:
            src_entries, src_errors, src_options = _parse_dirty_file(fpath, header)
        except OSError:
            return False
        if src_errors or src_options.get("include"):
            return False
        if any(isinstance(e, (data.Open, data.Close)) for e in src_entries):
            return False

    state.file_sigs.update(new_sigs)
    state.matched_globs = cur_globs
    state.included_realpaths = state.included_realpaths | set(new_sigs)
    return True


def _get_cached(path: str, *, schema_only: bool = False) -> _CachedLedger:
    abs_main = os.path.abspath(path)
    key = os.path.realpath(abs_main)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            watch = cached.schema if schema_only else cached.full
            if watch.is_fresh() or (schema_only and _try_advance_schema(cached)):
                _cache.move_to_end(key)
                return cached

        prev_scans = cached.include_scan_cache if cached is not None else None
        cached = _build_cached_ledger(abs_main, prev_scans=prev_scans)
        _cache[key] = cached
        _cache.move_to_end(key)
        while len(_cache) > _MAX_CACHED_LEDGERS:
            _cache.popitem(last=False)
        return cached


def _load(path: str):
    cached = _get_cached(path, schema_only=False)
    return cached.entries, cached.errors, cached.options_map


def included_files(main_path: str) -> set[str]:
    """Real paths of every file the ledger loads, including the main file.

    Uses the loader's own ``options_map["include"]`` so glob includes,
    relative paths, cycles, and missing includes are all handled by
    beancount itself — a textual walk of ``include`` directives would miss
    glob-covered files and cause duplicate includes downstream.
    """
    cached = _get_cached(main_path, schema_only=False)
    return set(cached.full.included_realpaths)


def load_accounts(path: str) -> list[str]:
    cached = _get_cached(path, schema_only=True)
    return sorted(
        acct for acct, (open_e, _close_e) in cached.open_close_map.items()
        if open_e is not None
    )


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
    reuse the locate load as its pre-delete baseline."""
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
    ``baseline`` (multiset diff)."""
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


def _parser_option_header(options_map: dict) -> str:
    """Emit minimal ``option`` directives for non-default parser-level options
    (custom root account names, pipe separator) so ``parser.parse_string``
    matches the main ledger's syntax rules."""
    lines: list[str] = []
    defaults = bc_options.OPTIONS_DEFAULTS
    for key in _PARSER_ROOT_OPTIONS:
        val = options_map.get(key)
        if val and val != defaults.get(key):
            escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'option "{key}" "{escaped}"')
    if options_map.get("allow_pipe_separator"):
        lines.append('option "allow_pipe_separator" "TRUE"')
    return ("\n".join(lines) + "\n") if lines else ""


def _initial_balances_for_accounts(
    entries: list, accounts: set[str], cutoff_date
) -> collections.defaultdict:
    balances: collections.defaultdict = collections.defaultdict(inventory.Inventory)
    for entry in entries:
        if entry.date > cutoff_date:
            break
        if isinstance(entry, data.Transaction):
            for posting in entry.postings:
                if posting.account in accounts:
                    balances[posting.account].add_position(posting)
    return balances


def _has_auto_accounts(options_map: dict) -> bool:
    return any(
        name in _AUTO_ACCOUNTS_PLUGINS
        for name, _cfg in options_map.get("plugin", [])
    )


def validate_snippet_with_includes(main_path: str, snippet: str) -> tuple[list[str], set[str]]:
    """Return ``(errors, included_realpaths)`` for appending ``snippet`` to
    the ledger.

    Validates ``snippet`` incrementally against the cached schema
    (``options_map`` and ``Open``/``Close`` directives); only loads full
    entries when the snippet contains cost-basis postings.
    """
    cached = _get_cached(main_path, schema_only=True)
    options_map = cached.options_map
    included = set(cached.schema.included_realpaths)

    parse_input = _parser_option_header(options_map) + snippet
    snippet_entries, parse_errors, _ = parser.parse_string(
        parse_input, report_filename=_SNIPPET_FILENAME
    )
    if parse_errors:
        return _error_messages(parse_errors), included
    if not snippet_entries:
        return [], included

    referenced_accounts: set[str] = set()
    cost_accounts: set[str] = set()
    max_txn_date = None
    for entry in snippet_entries:
        referenced_accounts.update(getters.get_entry_accounts(entry))
        if isinstance(entry, data.Transaction):
            if max_txn_date is None or entry.date > max_txn_date:
                max_txn_date = entry.date
            for posting in entry.postings:
                if posting.cost is not None:
                    cost_accounts.add(posting.account)

    rounding_account = options_map.get("account_rounding")
    if rounding_account:
        referenced_accounts.add(rounding_account)

    relevant_opens = [
        open_e
        for acct in referenced_accounts
        if (pair := cached.open_close_map.get(acct)) is not None
        and (open_e := pair[0]) is not None
    ]

    initial_balances = None
    if cost_accounts and max_txn_date is not None:
        full_cached = (
            cached if cached.full == cached.schema
            else _get_cached(main_path, schema_only=False)
        )
        initial_balances = _initial_balances_for_accounts(
            full_cached.entries, cost_accounts, max_txn_date
        )

    booked_entries, book_errors = booking.book(
        relevant_opens + snippet_entries,
        options_map,
        initial_balances=initial_balances,
    )
    errors = list(book_errors)

    snippet_booked = [
        e for e in booked_entries
        if (e.meta or {}).get("filename") == _SNIPPET_FILENAME
    ]
    if snippet_booked:
        post_accounts = set(referenced_accounts)
        for entry in snippet_booked:
            post_accounts.update(getters.get_entry_accounts(entry))
        relevant_open_close = [
            directive
            for acct in post_accounts
            if (pair := cached.open_close_map.get(acct)) is not None
            for directive in pair
            if directive is not None
        ]
        subset = sorted(relevant_open_close + snippet_booked, key=data.entry_sortkey)

        if _has_auto_accounts(options_map):
            subset, auto_errors = auto_accounts.auto_insert_open(subset, options_map)
            errors.extend(auto_errors)
        errors.extend(validation.validate_active_accounts(subset, options_map))
        errors.extend(validation.validate_currency_constraints(subset, options_map))
        errors.extend(
            validation.validate_check_transaction_balances(snippet_booked, options_map)
        )

    return _error_messages(errors), included


def validate_snippet(main_path: str, snippet: str) -> list[str]:
    """Return new error messages introduced by appending `snippet` to the ledger.

    Empty list means the snippet parses and balances against open accounts.
    """
    errors, _included = validate_snippet_with_includes(main_path, snippet)
    return errors
