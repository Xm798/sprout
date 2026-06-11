import datetime
import os
from pathlib import Path

from app.config import AppConfig
from app.ledger import included_files


def resolve_root(config: AppConfig) -> Path:
    return Path(config.ledger_root) if config.ledger_root else Path(config.ledger_main_file).parent


def target_path(config: AppConfig, when: datetime.date, target_file: str | None = None) -> Path:
    # A non-None target_file must already have passed validate_target_file.
    root = resolve_root(config)
    if target_file:
        return root / target_file
    if config.write_mode == "month_file":
        rel = config.month_file_template.format(year=when.year, month=when.month)
        return root / rel
    return root / config.single_file_name


def validate_target_file(config: AppConfig, value: str | None) -> str | None:
    """Normalize and validate a schedule's target_file.

    Returns the normalized relative path (POSIX separators) or None for
    blank input. Raises ValueError on invalid paths. The containment check
    resolves symlinks, so it is also re-run cheaply at confirm time to catch
    symlinks created after the schedule was saved.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if "\\" in value:
        raise ValueError("target_file must use forward slashes")
    if '"' in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("target_file must not contain quotes or control characters")
    p = Path(value)
    if p.is_absolute():
        raise ValueError("target_file must be a relative path")
    if ".." in p.parts:
        raise ValueError("target_file must not contain '..'")
    if p.suffix != ".bean":
        raise ValueError("target_file must end with .bean")
    root = resolve_root(config).resolve()
    if not (root / p).resolve().is_relative_to(root):
        raise ValueError("target_file must stay inside the ledger root")
    return p.as_posix()


def append_transaction(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text() if path.exists() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_content = existing + text
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_content)
    os.replace(tmp, path)


def replace_file(path: Path, content: bytes) -> None:
    """Atomically replace ``path``'s content byte-for-byte (tmp + os.replace).
    Also the restore half of verify-restore flows: writing back a snapshot
    taken with ``read_bytes`` is guaranteed byte-identical."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content)
    os.replace(tmp, path)


def _block_lines(path: Path, lineno: int) -> tuple[list[bytes], int, int]:
    """Split ``path`` into lines and return ``(lines, start, end)`` for the
    entry block whose header sits at ``lineno`` (1-based): the header plus
    every following blank or indented line — tabs count as indentation.
    Byte-level on purpose: ``str.splitlines`` also breaks on unicode line
    separators that may legally appear inside quoted strings."""
    lines = Path(path).read_bytes().splitlines(keepends=True)
    start = lineno - 1
    if not 0 <= start < len(lines):
        raise ValueError(f"line {lineno} is outside {path}")
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (b" ", b"\t")):
        end += 1
    return lines, start, end


def _block_text(lines: list[bytes], start: int, end: int) -> str:
    block = b"".join(lines[start:end])
    return (block.rstrip(b"\r\n") + b"\n").decode("utf-8")


def read_block(path: Path, lineno: int) -> str:
    """The entry block whose header sits at ``lineno``, exactly as it exists
    on disk (trailing blank lines trimmed)."""
    lines, start, end = _block_lines(path, lineno)
    return _block_text(lines, start, end)


def delete_block(path: Path, lineno: int) -> str:
    """Remove the entry block whose header sits at ``lineno`` (1-based).

    Pure line surgery: the block and its surrounding blank separation are
    removed, collapsing to a single blank line between the neighbours (none
    at the file edges); nothing outside the block is reformatted. Atomic
    tmp+replace write; returns the removed block text.

    Known limitation: a multi-line quoted string (legal beancount) puts its
    continuation text at column 0, ending the block early here — callers must
    verify the ledger still loads afterwards and restore on failure.
    """
    lines, start, end = _block_lines(path, lineno)
    pre = start
    while pre > 0 and not lines[pre - 1].strip():
        pre -= 1
    head, tail = lines[:pre], lines[end:]
    separator = b"\n" if head and tail else b""
    replace_file(path, b"".join(head) + separator + b"".join(tail))
    return _block_text(lines, start, end)


def ensure_included(config: AppConfig, target: Path) -> None:
    """Make `target` loadable from the main ledger.

    Creates the file when missing (an include whose glob matches no file is
    a beancount error, so creation must precede the reachability check),
    then appends an include line to the main file unless the target is
    already reachable — directly, via a sub-file, or via a glob include.
    Integrates whatever path it is given; callers are responsible for
    validating it (validate_target_file) beforehand.
    """
    if target.is_dir():
        raise ValueError("target_file is a directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.touch()
    main = Path(config.ledger_main_file).resolve()
    rel = Path(os.path.relpath(target.resolve(), main.parent)).as_posix()
    include_line = f'include "{rel}"'
    # The include path is interpolated into the ledger unescaped; a quote
    # would bake a permanent parse error into the main file. validate_target_file
    # rejects quotes in target_file, but rel can also inherit one from the
    # configured root/main paths — guard at the interpolation itself.
    if '"' in rel:
        raise ValueError("include path must not contain quotes")
    # Fast path: the exact line this function appends is already present.
    # Skips the full-ledger reachability load on every steady-state confirm;
    # glob/sub-file-reachable targets fall through to the loader check.
    main_text = main.read_text() if main.exists() else ""
    if any(line.strip() == include_line for line in main_text.splitlines()):
        return
    if os.path.realpath(target) in included_files(str(main)):
        return
    append_transaction(main, include_line + "\n")
