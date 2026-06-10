import datetime
from pathlib import Path

from app.config import AppConfig
from app.writer import target_path, append_transaction


def _cfg(tmp_path, **kw):
    base = dict(
        id=1, ledger_main_file=str(tmp_path / "main.bean"),
        ledger_root=str(tmp_path), write_mode="single_file",
        single_file_name="sprout.bean",
        month_file_template="transactions/{year}/{year}-{month:02d}.bean",
    )
    base.update(kw)
    return AppConfig(**base)


def test_single_file_target(tmp_path):
    cfg = _cfg(tmp_path)
    p = target_path(cfg, datetime.date(2026, 6, 15))
    assert p == Path(tmp_path) / "sprout.bean"


def test_month_file_target(tmp_path):
    cfg = _cfg(tmp_path, write_mode="month_file")
    p = target_path(cfg, datetime.date(2026, 6, 15))
    assert p == Path(tmp_path) / "transactions" / "2026" / "2026-06.bean"


def test_root_defaults_to_main_dir(tmp_path):
    cfg = _cfg(tmp_path, ledger_root="")
    p = target_path(cfg, datetime.date(2026, 6, 15))
    assert p == Path(tmp_path) / "sprout.bean"


def test_target_file_overrides_single_file_mode(tmp_path):
    cfg = _cfg(tmp_path)
    p = target_path(cfg, datetime.date(2026, 6, 15), target_file="rent.bean")
    assert p == Path(tmp_path) / "rent.bean"


def test_target_file_overrides_month_file_mode(tmp_path):
    cfg = _cfg(tmp_path, write_mode="month_file")
    p = target_path(cfg, datetime.date(2026, 6, 15), target_file="loans/mortgage.bean")
    assert p == Path(tmp_path) / "loans" / "mortgage.bean"


def test_target_file_uses_root_fallback(tmp_path):
    cfg = _cfg(tmp_path, ledger_root="")
    p = target_path(cfg, datetime.date(2026, 6, 15), target_file="rent.bean")
    assert p == Path(tmp_path) / "rent.bean"  # falls back to main file's directory


def test_append_creates_and_appends(tmp_path):
    cfg = _cfg(tmp_path)
    p = target_path(cfg, datetime.date(2026, 6, 15))
    append_transaction(p, "ENTRY-A\n")
    append_transaction(p, "ENTRY-B\n")
    content = p.read_text()
    assert "ENTRY-A" in content
    assert content.index("ENTRY-A") < content.index("ENTRY-B")
    assert not list(p.parent.glob("*.tmp"))  # no leftover temp file
