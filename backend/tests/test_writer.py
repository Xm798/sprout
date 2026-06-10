import datetime
from pathlib import Path

import pytest

from app.config import AppConfig
from app.writer import target_path, append_transaction, validate_target_file, ensure_included


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


def test_validate_target_file_accepts_nested(tmp_path):
    cfg = _cfg(tmp_path)
    assert validate_target_file(cfg, "loans/mortgage.bean") == "loans/mortgage.bean"


def test_validate_target_file_normalizes_blank_to_none(tmp_path):
    cfg = _cfg(tmp_path)
    assert validate_target_file(cfg, None) is None
    assert validate_target_file(cfg, "") is None
    assert validate_target_file(cfg, "   ") is None


@pytest.mark.parametrize("bad", [
    "/abs/x.bean",        # absolute
    "../up.bean",         # parent escape
    "a/../../up.bean",    # nested parent escape
    "rent.txt",           # wrong extension
    "rent",               # no extension
    "a\\b.bean",          # backslash
])
def test_validate_target_file_rejects(tmp_path, bad):
    cfg = _cfg(tmp_path)
    with pytest.raises(ValueError):
        validate_target_file(cfg, bad)


def test_validate_target_file_rejects_symlink_escape(tmp_path):
    root = tmp_path / "ledger"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    cfg = _cfg(tmp_path, ledger_root=str(root), ledger_main_file=str(root / "main.bean"))
    with pytest.raises(ValueError):
        validate_target_file(cfg, "link/x.bean")


def _main_ledger(tmp_path, content='option "operating_currency" "USD"\n') -> Path:
    main = tmp_path / "main.bean"
    main.write_text(content)
    return main


def test_ensure_included_creates_file_and_appends_include(tmp_path):
    cfg = _cfg(tmp_path)
    main = _main_ledger(tmp_path)
    target = tmp_path / "rent.bean"
    ensure_included(cfg, target)
    assert target.exists()
    assert 'include "rent.bean"' in main.read_text()


def test_ensure_included_is_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    main = _main_ledger(tmp_path)
    target = tmp_path / "rent.bean"
    ensure_included(cfg, target)
    ensure_included(cfg, target)
    assert main.read_text().count('include "rent.bean"') == 1


def test_ensure_included_respects_glob_include(tmp_path):
    cfg = _cfg(tmp_path)
    main = _main_ledger(tmp_path, 'include "txns/*.bean"\n')
    target = tmp_path / "txns" / "rent.bean"
    ensure_included(cfg, target)
    # the file is created first, so the glob matches it -> reachable -> no new include
    assert "rent.bean" not in main.read_text()


def test_ensure_included_respects_subfile_include(tmp_path):
    cfg = _cfg(tmp_path)
    main = _main_ledger(tmp_path, 'include "sub.bean"\n')
    (tmp_path / "sub.bean").write_text('include "rent.bean"\n')
    (tmp_path / "rent.bean").write_text("")
    ensure_included(cfg, tmp_path / "rent.bean")
    assert main.read_text().count("include") == 1  # only the original sub.bean include


def test_ensure_included_never_self_includes_main(tmp_path):
    cfg = _cfg(tmp_path)
    main = _main_ledger(tmp_path)
    ensure_included(cfg, main)
    assert "include" not in main.read_text()


def test_ensure_included_relpath_when_root_differs_from_main_dir(tmp_path):
    # main lives in books/, root is tmp_path -> include path needs a ../ prefix
    (tmp_path / "books").mkdir()
    main = tmp_path / "books" / "main.bean"
    main.write_text("")
    cfg = _cfg(tmp_path, ledger_main_file=str(main))
    ensure_included(cfg, tmp_path / "rent.bean")
    assert 'include "../rent.bean"' in main.read_text()
