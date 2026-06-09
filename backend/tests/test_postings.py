from app.postings import (
    Posting, Cost, Price, parse_postings, dump_postings,
    validate_postings, headline, struct_key,
)


def _amount_leg(**kw):
    base = dict(id="p1", account="Expenses:Food", amount="15.00", currency="USD")
    base.update(kw)
    return Posting(**base)


def test_parse_and_dump_roundtrip():
    raw = [
        {"id": "p1", "account": "Expenses:Food", "amount": "15.00", "currency": "USD",
         "cost": None, "price": None},
        {"id": "p2", "account": "Assets:Cash", "amount": None, "currency": None,
         "cost": None, "price": None},
    ]
    postings = parse_postings(raw)
    assert postings[0].amount == "15.00"
    assert postings[1].amount is None
    assert dump_postings(postings) == raw


def test_validate_ok_two_leg():
    postings = [_amount_leg(), Posting(id="p2", account="Assets:Cash")]
    assert validate_postings(postings) == []


def test_validate_requires_two_postings():
    assert "at least 2 postings" in " ".join(validate_postings([_amount_leg()]))


def test_validate_at_most_one_blank_leg():
    postings = [
        _amount_leg(),
        Posting(id="p2", account="Assets:Cash"),
        Posting(id="p3", account="Assets:Other"),
    ]
    assert "one posting may have a blank amount" in " ".join(validate_postings(postings))


def test_validate_amount_requires_currency():
    postings = [_amount_leg(currency=None), Posting(id="p2", account="Assets:Cash")]
    assert "requires a currency" in " ".join(validate_postings(postings))


def test_validate_cost_price_only_on_amount_leg():
    postings = [
        _amount_leg(),
        Posting(id="p2", account="Assets:Cash", price=Price(amount="1.1", currency="USD")),
    ]
    assert "requires an amount" in " ".join(validate_postings(postings))


def test_validate_require_blank_leg_flag():
    postings = [_amount_leg(), _amount_leg(id="p2", account="Income:Salary", amount="-15.00")]
    assert "blank" in " ".join(validate_postings(postings, require_blank_leg=True))
    assert not validate_postings(
        [_amount_leg(), Posting(id="p2", account="Assets:Cash")], require_blank_leg=True
    )


def test_headline_first_amount_leg():
    postings = [
        Posting(id="p0", account="Assets:Cash"),
        _amount_leg(id="p1", amount="42.00", currency="EUR"),
    ]
    assert headline(postings) == ("42.00", "EUR")


def test_struct_key_ignores_amount():
    a = _amount_leg(amount="15.00")
    b = _amount_leg(amount="99.00")
    assert struct_key(a) == struct_key(b)
    c = _amount_leg(account="Expenses:Other")
    assert struct_key(a) != struct_key(c)
