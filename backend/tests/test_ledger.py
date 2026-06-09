from app.ledger import load_accounts, load_currencies
from app.ledger import validate_snippet


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
