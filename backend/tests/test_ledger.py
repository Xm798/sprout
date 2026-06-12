import os

import pytest

from app.ledger import ConflictError, find_transaction
from app.ledger import load_accounts, load_currencies
from app.ledger import validate_snippet
from app.ledger import included_files


def test_load_accounts(demo_ledger):
    accounts = load_accounts(demo_ledger)
    assert "Assets:CreditCard" in accounts
    assert "Expenses:Subscription" in accounts
    assert accounts == sorted(accounts)


def test_load_currencies(demo_ledger):
    currencies = load_currencies(demo_ledger)
    assert currencies == ["USD", "CNY"]


def test_load_currencies_includes_referenced_commodities(tmp_path):
    ledger = tmp_path / "ledger.bean"
    ledger.write_text(
        'option "operating_currency" "USD"\n\n'
        "2020-01-01 commodity EUR\n"
        "2020-01-01 open Assets:Cash\n"
        "2020-01-01 open Assets:Euro EUR\n"
        "2020-01-01 open Expenses:Misc\n\n"
        '2021-01-01 * "x"\n'
        "  Expenses:Misc   10.00 GBP\n"
        "  Assets:Cash    -10.00 GBP\n"
    )
    # Operating currency first, other referenced commodities appended sorted.
    assert load_currencies(str(ledger)) == ["USD", "EUR", "GBP"]


def test_valid_snippet_has_no_errors(demo_ledger):
    snippet = (
        '2026-06-15 * "Spotify" "sub"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    assert validate_snippet(demo_ledger, snippet) == []


def test_unknown_account_is_reported(demo_ledger):
    snippet = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:DoesNotExist  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    errors = validate_snippet(demo_ledger, snippet)
    assert errors  # at least one error about the undeclared account


def test_unbalanced_snippet_is_reported(demo_ledger):
    snippet = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard  -10.00 USD\n"
    )
    errors = validate_snippet(demo_ledger, snippet)
    assert errors


def test_included_files_walks_globs_and_subfiles(tmp_path):
    main = tmp_path / "main.bean"
    main.write_text('include "sub.bean"\ninclude "txns/*.bean"\n')
    (tmp_path / "sub.bean").write_text('include "nested.bean"\n')
    (tmp_path / "nested.bean").write_text("")
    (tmp_path / "txns").mkdir()
    (tmp_path / "txns" / "a.bean").write_text("")

    files = included_files(str(main))

    assert os.path.realpath(str(main)) in files          # main itself is in the set
    assert os.path.realpath(str(tmp_path / "sub.bean")) in files
    assert os.path.realpath(str(tmp_path / "nested.bean")) in files
    assert os.path.realpath(str(tmp_path / "txns" / "a.bean")) in files


def test_included_files_tolerates_missing_include(tmp_path):
    main = tmp_path / "main.bean"
    main.write_text('include "ghost/*.bean"\n')
    files = included_files(str(main))
    assert os.path.realpath(str(main)) in files


# ── find_transaction ───────────────────────────────────────────────────────────

TXN = (
    '2026-01-15 * "Spotify" "sub" #sprout\n'
    '  sprout-id: "sch1-20260115"\n'
    "  Expenses:Subscription  15.00 USD\n"
    "  Assets:CreditCard\n"
)


def _tree(tmp_path):
    sub = tmp_path / "sub.bean"
    sub.write_text("\n" + TXN)
    main = tmp_path / "main.bean"
    main.write_text(
        "2020-01-01 open Assets:CreditCard\n"
        "2020-01-01 open Expenses:Subscription\n"
        'include "sub.bean"\n'
    )
    return main, sub


def test_find_transaction_reports_file_and_header_line(tmp_path):
    main, sub = _tree(tmp_path)
    path, lineno = find_transaction(str(main), "sch1-20260115")
    assert os.path.realpath(path) == os.path.realpath(str(sub))
    assert lineno == 2  # 1-based header line, after the leading blank


def test_find_transaction_absent_returns_none(tmp_path):
    main, _sub = _tree(tmp_path)
    assert find_transaction(str(main), "sch9-19990101") is None


def test_find_transaction_missing_main_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        find_transaction(str(tmp_path / "nope.bean"), "x")
    with pytest.raises(FileNotFoundError):
        find_transaction("", "x")


def test_find_transaction_duplicate_id_conflict(tmp_path):
    main, sub = _tree(tmp_path)
    sub.write_text(sub.read_text() + "\n" + TXN.replace("2026-01-15", "2026-02-15"))
    with pytest.raises(ConflictError):
        find_transaction(str(main), "sch1-20260115")
