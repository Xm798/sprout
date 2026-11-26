import os
from unittest.mock import MagicMock

from beancount import loader
import pytest

from app import ledger
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


def test_cache_reuses_loaded_ledger_until_file_changes(tmp_path, monkeypatch):
    main = tmp_path / "main.bean"
    main.write_text(
        "2020-01-01 open Assets:CreditCard\n"
        "2020-01-01 open Expenses:Subscription\n"
    )
    ledger.clear_cache()

    spy = MagicMock(wraps=loader.load_file)
    monkeypatch.setattr(loader, "load_file", spy)

    snippet = (
        '2026-06-15 * "Spotify" "sub"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    assert validate_snippet(str(main), snippet) == []
    assert validate_snippet(str(main), snippet) == []
    assert load_accounts(str(main)) == ["Assets:CreditCard", "Expenses:Subscription"]
    assert included_files(str(main)) == {os.path.realpath(str(main))}
    assert spy.call_count == 1

    main.write_text(main.read_text() + "2020-01-01 open Expenses:Music\n")
    assert "Expenses:Music" in load_accounts(str(main))
    assert spy.call_count == 2


def test_cache_invalidates_on_new_glob_included_file(tmp_path):
    ledger.clear_cache()
    txns_dir = tmp_path / "txns"
    txns_dir.mkdir()
    (txns_dir / "a.bean").write_text("2020-01-01 open Assets:A\n")
    main = tmp_path / "main.bean"
    main.write_text('include "txns/*.bean"\n')

    assert load_accounts(str(main)) == ["Assets:A"]
    assert os.path.realpath(str(txns_dir / "a.bean")) in included_files(str(main))

    (txns_dir / "b.bean").write_text("2020-01-01 open Assets:B\n")
    assert load_accounts(str(main)) == ["Assets:A", "Assets:B"]
    assert os.path.realpath(str(txns_dir / "b.bean")) in included_files(str(main))


def test_cache_invalidates_when_previously_missing_include_appears(tmp_path):
    ledger.clear_cache()
    main = tmp_path / "main.bean"
    main.write_text(
        "2020-01-01 open Assets:CreditCard\n"
        "2020-01-01 open Expenses:Subscription\n"
        'include "sprout.bean"\n'
    )
    assert ledger.load_sprout_ids(str(main)) == set()

    (tmp_path / "sprout.bean").write_text(TXN)
    assert ledger.load_sprout_ids(str(main)) == {"sch1-20260115"}


def test_schema_cache_reloads_when_dirty_file_adds_open_directive(tmp_path, monkeypatch):
    ledger.clear_cache()
    txns = tmp_path / "txns.bean"
    txns.write_text(TXN)
    main = tmp_path / "main.bean"
    main.write_text(
        "2020-01-01 open Assets:CreditCard\n"
        "2020-01-01 open Expenses:Subscription\n"
        'include "txns.bean"\n'
    )

    spy = MagicMock(wraps=loader.load_file)
    monkeypatch.setattr(loader, "load_file", spy)

    assert load_accounts(str(main)) == ["Assets:CreditCard", "Expenses:Subscription"]
    assert spy.call_count == 1

    # Appending another transaction advances schema state without full reload.
    txns.write_text(txns.read_text() + "\n" + TXN.replace("2026-01-15", "2026-02-15"))
    assert load_accounts(str(main)) == ["Assets:CreditCard", "Expenses:Subscription"]
    assert spy.call_count == 1

    # Adding an Open directive in the same file triggers a full reload.
    txns.write_text(txns.read_text() + "\n2020-01-01 open Expenses:Music\n")
    assert "Expenses:Music" in load_accounts(str(main))
    assert spy.call_count == 2


def test_fast_validate_catches_closed_future_currency_syntax_and_missing_legs(tmp_path):
    main = tmp_path / "main.bean"
    main.write_text(
        "2020-01-01 open Assets:CreditCard USD\n"
        "2020-01-01 open Expenses:Subscription\n"
        "2020-01-01 open Assets:OldBank\n"
        "2025-01-01 close Assets:OldBank\n"
        "2026-07-01 open Assets:FutureBank\n"
    )

    closed = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:OldBank\n"
    )
    assert any("inactive" in e for e in validate_snippet(str(main), closed))

    future = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:FutureBank\n"
    )
    assert any("inactive" in e for e in validate_snippet(str(main), future))

    wrong_ccy = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:Subscription  15.00 EUR\n"
        "  Assets:CreditCard\n"
    )
    assert any("Invalid currency" in e for e in validate_snippet(str(main), wrong_ccy))

    two_missing = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:Subscription\n"
        "  Assets:CreditCard\n"
    )
    assert validate_snippet(str(main), two_missing)

    bad_syntax = '2026-99-99 * "X" "y"\n  Expenses:Subscription  15.00 USD\n'
    assert validate_snippet(str(main), bad_syntax)


def test_fast_validate_honors_custom_root_account_names(tmp_path):
    main = tmp_path / "main.bean"
    main.write_text(
        'option "name_assets" "Zichan"\n'
        "2020-01-01 open Zichan:Bank\n"
        "2020-01-01 open Expenses:Food\n"
    )
    snippet = (
        '2026-06-15 * "Lunch" "noodles"\n'
        "  Expenses:Food  20.00 CNY\n"
        "  Zichan:Bank\n"
    )
    assert validate_snippet(str(main), snippet) == []


def test_fast_validate_honors_auto_accounts_plugin(tmp_path):
    main = tmp_path / "main.bean"
    main.write_text(
        'plugin "beancount.plugins.auto_accounts"\n'
        "2020-01-01 open Assets:Old\n"
        "2025-01-01 close Assets:Old\n"
    )
    new_accts = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:BrandNew  10.00 USD\n"
        "  Assets:BrandNew\n"
    )
    assert validate_snippet(str(main), new_accts) == []

    closed_acct = (
        '2026-06-15 * "X" "y"\n'
        "  Expenses:BrandNew  10.00 USD\n"
        "  Assets:Old\n"
    )
    assert any("inactive" in e for e in validate_snippet(str(main), closed_acct))


def test_fast_validate_supports_cost_lot_reduction(tmp_path):
    main = tmp_path / "main.bean"
    main.write_text(
        "2020-01-01 open Assets:Broker\n"
        "2020-01-01 open Assets:Cash\n"
        "2020-01-01 open Income:PnL\n"
        '2020-02-01 * "Buy"\n'
        "  Assets:Broker  10 AAPL {100.00 USD}\n"
        "  Assets:Cash   -1000.00 USD\n"
    )
    sell = (
        '2026-06-15 * "Sell"\n'
        "  Assets:Broker  -5 AAPL {} @ 120.00 USD\n"
        "  Assets:Cash     600.00 USD\n"
        "  Income:PnL\n"
    )
    assert validate_snippet(str(main), sell) == []
