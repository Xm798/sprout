import datetime

from app.bean_format import format_transaction
from app.postings import Posting, Cost, Price


def test_two_leg_with_tag_and_meta():
    text = format_transaction(
        date=datetime.date(2026, 6, 15),
        payee="Spotify",
        narration="subscription",
        postings=[
            Posting(id="a", account="Expenses:Subscription", amount="15.00", currency="USD"),
            Posting(id="b", account="Assets:CreditCard"),
        ],
        tags=["sprout"],
        meta={"sprout-id": "sch1-20260615"},
    )
    assert text == (
        '2026-06-15 * "Spotify" "subscription" #sprout\n'
        '  sprout-id: "sch1-20260615"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )


def test_integer_amount_renders_bare():
    text = format_transaction(
        date=datetime.date(2026, 6, 1),
        payee="Rent",
        narration="",
        postings=[
            Posting(id="a", account="Expenses:Housing:Rent", amount="1200", currency="USD"),
            Posting(id="b", account="Assets:Bank:Checking"),
        ],
    )
    assert text == (
        '2026-06-01 * "Rent" ""\n'
        "  Expenses:Housing:Rent  1200 USD\n"
        "  Assets:Bank:Checking\n"
    )


def test_cost_and_price_render_order():
    text = format_transaction(
        date=datetime.date(2026, 6, 1),
        payee="Broker",
        narration="buy",
        postings=[
            Posting(
                id="a", account="Assets:Stock", amount="10", currency="ACME",
                cost=Cost(amount="100.00", currency="USD"),
                price=Price(amount="105.00", currency="USD"),
            ),
            Posting(id="b", account="Assets:Cash"),
        ],
    )
    assert text == (
        '2026-06-01 * "Broker" "buy"\n'
        "  Assets:Stock  10 ACME {100.00 USD} @ 105.00 USD\n"
        "  Assets:Cash\n"
    )


def test_total_cost_and_total_price():
    text = format_transaction(
        date=datetime.date(2026, 6, 1),
        payee="FX",
        narration="",
        postings=[
            Posting(
                id="a", account="Assets:EUR", amount="100", currency="EUR",
                price=Price(amount="110.00", currency="USD", total=True),
            ),
            Posting(
                id="b", account="Assets:Lot", amount="5", currency="ACME",
                cost=Cost(amount="500.00", currency="USD", total=True),
            ),
            Posting(id="c", account="Assets:Cash"),
        ],
    )
    assert text == (
        '2026-06-01 * "FX" ""\n'
        "  Assets:EUR  100 EUR @@ 110.00 USD\n"
        "  Assets:Lot  5 ACME {{500.00 USD}}\n"
        "  Assets:Cash\n"
    )
