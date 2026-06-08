from app.ledger import load_accounts, load_currencies


def test_load_accounts(demo_ledger):
    accounts = load_accounts(demo_ledger)
    assert "Assets:CreditCard" in accounts
    assert "Expenses:Subscription" in accounts
    assert accounts == sorted(accounts)


def test_load_currencies(demo_ledger):
    currencies = load_currencies(demo_ledger)
    assert currencies == ["USD", "CNY"]
