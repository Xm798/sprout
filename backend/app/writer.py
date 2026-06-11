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


def ensure_included(config: AppConfig, target: Path) -> None:
    """Make `target` loadable from the main ledger.

    Creates the file when missing (an include whose glob matches no file is
    a beancount error, so creation must precede the reachability check),
    then appends an include line to the main file unless the target is
    already reachable — directly, via a sub-file, or via a glob include.
    Integrates whatever path it is given; callers are responsible for
    validating it (validate_target_file) beforehand.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.touch()
    main = Path(config.ledger_main_file).resolve()
    if os.path.realpath(target) in included_files(str(main)):
        return
    rel = Path(os.path.relpath(target.resolve(), main.parent)).as_posix()
    append_transaction(main, f'include "{rel}"\n')
