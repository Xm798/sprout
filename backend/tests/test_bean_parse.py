import datetime

import pytest

from app.bean_parse import parse_transaction, ParseError
from app.bean_format import format_transaction
from app.postings import Posting, Cost, Price


def _legs(parsed):
    """Postings with the random id dropped, for structural comparison."""
    return [p.model_dump(exclude={"id"}) for p in parsed.postings]


def test_single_two_leg():
    parsed = parse_transaction(
        '2026-06-15 * "Spotify" "subscription"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    assert parsed.payee == "Spotify"
    assert parsed.narration == "subscription"
    assert parsed.anchor_date == datetime.date(2026, 6, 15)
    assert _legs(parsed) == [
        {"account": "Expenses:Subscription", "amount": "15.00", "currency": "USD",
         "cost": None, "price": None},
        {"account": "Assets:CreditCard", "amount": None, "currency": None,
         "cost": None, "price": None},
    ]
    assert all(p.id for p in parsed.postings)
    assert parsed.warnings == []


def test_auto_balance_leg_is_missing_not_none():
    parsed = parse_transaction(
        '2026-06-01 * "x" ""\n  Assets:B  1 USD\n  Equity:D\n'
    )
    assert parsed.postings[1].amount is None
    assert parsed.postings[1].currency is None


def test_integer_amount_canonical():
    parsed = parse_transaction(
        '2026-06-01 * "Rent" ""\n  Expenses:Rent  1200 USD\n  Assets:Bank\n'
    )
    assert parsed.postings[0].amount == "1200"


def test_amount_strips_to_two_decimals_like_renderer():
    parsed = parse_transaction(
        '2026-06-01 * "x" ""\n  Assets:B  100.000 USD\n  Equity:D\n'
    )
    assert parsed.postings[0].amount == "100.00"


def test_per_unit_cost():
    parsed = parse_transaction(
        '2026-06-01 * "x" ""\n  Assets:Stock  10 ACME {100.00 USD}\n  Assets:Cash\n'
    )
    assert parsed.postings[0].cost == Cost(amount="100.00", currency="USD", total=False)


def test_total_cost():
    parsed = parse_transaction(
        '2026-06-01 * "x" ""\n  Assets:Lot  5 ACME {{500.00 USD}}\n  Assets:Cash\n'
    )
    assert parsed.postings[0].cost == Cost(amount="500.00", currency="USD", total=True)


def test_per_unit_price():
    parsed = parse_transaction(
        '2026-06-01 * "x" ""\n  Assets:Stock  10 ACME @ 105.00 USD\n  Assets:Cash\n'
    )
    assert parsed.postings[0].price == Price(amount="105.00", currency="USD", total=False)


def test_total_price_uses_source_total_not_normalized_per_unit():
    # beancount normalizes @@ to a per-unit price (1.10); we must recover the
    # written total (110.00) and total=True from the source text.
    parsed = parse_transaction(
        '2026-06-01 * "FX" ""\n  Assets:EUR  100 EUR @@ 110.00 USD\n  Assets:Cash\n'
    )
    assert parsed.postings[0].price == Price(amount="110.00", currency="USD", total=True)


def test_tags_sorted_and_links_dropped():
    parsed = parse_transaction(
        '2026-06-01 * "x" "" #foo #bar ^lnk\n  Assets:B  1 USD\n  Equity:D\n'
    )
    assert parsed.tags == "bar,foo"


def test_no_tags_is_empty_string():
    parsed = parse_transaction('2026-06-01 * "x" ""\n  Assets:B  1 USD\n  Equity:D\n')
    assert parsed.tags == ""


def test_single_string_is_narration_with_empty_payee():
    parsed = parse_transaction('2026-06-01 * "only narration"\n  Assets:B  1 USD\n  Equity:D\n')
    assert parsed.payee == ""
    assert parsed.narration == "only narration"


def test_unrepresentable_elements_silently_dropped():
    # cost lot-date/label, posting metadata, links, non-* flag, sprout-id: all dropped.
    parsed = parse_transaction(
        '2026-06-01 ! "Broker" "buy" #t ^lnk\n'
        '  sprout-id: "sch9-20200101"\n'
        '  Assets:Stock  5 ACME {100.00 USD, 2020-01-01, "lot-a"}\n'
        '    note: "hi"\n'
        "  Assets:Cash\n"
    )
    assert parsed.postings[0].cost == Cost(amount="100.00", currency="USD", total=False)
    assert parsed.tags == "t"
    # no exception, no leaked metadata/links anywhere in the structure
    assert parsed.payee == "Broker"
    assert parsed.narration == "buy"


def test_structural_warning_single_posting():
    parsed = parse_transaction('2026-06-01 * "x" ""\n  Assets:B  1 USD\n')
    assert parsed.warnings  # at least one structural warning
    assert parsed.postings[0].account == "Assets:B"


def test_empty_text_raises():
    with pytest.raises(ParseError):
        parse_transaction("")


def test_no_transaction_raises():
    with pytest.raises(ParseError):
        parse_transaction('2026-06-01 open Assets:Bank\n')


def test_multiple_transactions_raises():
    with pytest.raises(ParseError):
        parse_transaction(
            '2026-06-01 * "a" ""\n  Assets:B 1 USD\n  Equity:D\n'
            '2026-06-02 * "b" ""\n  Assets:B 2 USD\n  Equity:D\n'
        )


def test_syntax_error_raises():
    with pytest.raises(ParseError):
        parse_transaction("not a ledger @@@ 2026-13-99")


def test_non_transaction_directives_ignored():
    parsed = parse_transaction(
        "2026-06-01 price ACME 100 USD\n"
        '2026-06-01 * "x"\n  Assets:B  1 USD\n  Equity:D\n'
    )
    assert parsed.payee == ""
    assert parsed.narration == "x"


@pytest.mark.parametrize("postings", [
    [Posting(id="a", account="Expenses:Sub", amount="15.00", currency="USD"),
     Posting(id="b", account="Assets:Card")],
    [Posting(id="a", account="Assets:Stock", amount="10", currency="ACME",
             cost=Cost(amount="100.00", currency="USD"),
             price=Price(amount="105.00", currency="USD")),
     Posting(id="b", account="Assets:Cash")],
    [Posting(id="a", account="Assets:EUR", amount="100", currency="EUR",
             price=Price(amount="110.00", currency="USD", total=True)),
     Posting(id="b", account="Assets:Lot", amount="5", currency="ACME",
             cost=Cost(amount="500.00", currency="USD", total=True)),
     Posting(id="c", account="Assets:Cash")],
])
def test_structural_roundtrip(postings):
    # parse(format(P)) reproduces P structurally (ids differ; amounts as written).
    text = format_transaction(
        date=datetime.date(2026, 6, 1), payee="P", narration="n",
        postings=postings, tags=["sprout"],
    )
    parsed = parse_transaction(text)
    assert parsed.payee == "P"
    assert parsed.narration == "n"
    assert parsed.tags == "sprout"
    assert _legs(parsed) == [p.model_dump(exclude={"id"}) for p in postings]
