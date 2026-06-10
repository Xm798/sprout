import datetime
import os
from pathlib import Path

from app.config import AppConfig


def resolve_root(config: AppConfig) -> Path:
    return Path(config.ledger_root) if config.ledger_root else Path(config.ledger_main_file).parent


def target_path(config: AppConfig, when: datetime.date, target_file: str | None = None) -> Path:
    root = resolve_root(config)
    if target_file:
        return root / target_file
    if config.write_mode == "month_file":
        rel = config.month_file_template.format(year=when.year, month=when.month)
        return root / rel
    return root / config.single_file_name


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
