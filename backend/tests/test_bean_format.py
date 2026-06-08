import datetime
from decimal import Decimal

from app.bean_format import format_transaction


def test_two_leg_with_tag_and_meta():
    text = format_transaction(
        date=datetime.date(2026, 6, 15),
        payee="Spotify",
        narration="subscription",
        postings=[
            ("Expenses:Subscription", Decimal("15.00"), "USD"),
            ("Assets:CreditCard", None, None),
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


def test_no_narration_no_tags():
    text = format_transaction(
        date=datetime.date(2026, 6, 1),
        payee="Rent",
        narration="",
        postings=[
            ("Expenses:Housing:Rent", Decimal("1200"), "USD"),
            ("Assets:Bank:Checking", None, None),
        ],
        tags=[],
        meta=None,
    )
    assert text == (
        '2026-06-01 * "Rent" ""\n'
        "  Expenses:Housing:Rent  1200 USD\n"
        "  Assets:Bank:Checking\n"
    )
