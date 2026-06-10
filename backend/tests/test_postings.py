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


def test_validate_rejects_non_decimal_amount():
    bad = _amount_leg(amount="abc")
    blank = Posting(id="p2", account="Assets:Cash")
    errors = validate_postings([bad, blank])
    assert any("not a number" in e for e in errors)


def test_validate_accepts_valid_decimal_amount():
    good = _amount_leg(amount="42.50")
    blank = Posting(id="p2", account="Assets:Cash")
    assert validate_postings([good, blank]) == []


# --- Defect 1: non-finite decimal values must be rejected ---

def test_validate_rejects_nan_amount():
    bad = _amount_leg(amount="NaN")
    blank = Posting(id="p2", account="Assets:Cash")
    errors = validate_postings([bad, blank])
    assert any("not a number" in e for e in errors)


def test_validate_rejects_infinity_amount():
    bad = _amount_leg(amount="Infinity")
    blank = Posting(id="p2", account="Assets:Cash")
    errors = validate_postings([bad, blank])
    assert any("not a number" in e for e in errors)


def test_validate_rejects_negative_infinity_amount():
    bad = _amount_leg(amount="-Infinity")
    blank = Posting(id="p2", account="Assets:Cash")
    errors = validate_postings([bad, blank])
    assert any("not a number" in e for e in errors)


# --- Defect 2: duplicate posting ids must be rejected ---

def test_validate_rejects_duplicate_posting_ids():
    p1 = _amount_leg(id="p1", account="Expenses:Food", amount="10.00")
    p2 = _amount_leg(id="p1", account="Expenses:Other", amount="5.00")  # duplicate id
    blank = Posting(id="p3", account="Assets:Cash")
    errors = validate_postings([p1, p2, blank])
    assert any("p1" in e for e in errors)


def test_validate_accepts_unique_posting_ids():
    p1 = _amount_leg(id="p1")
    blank = Posting(id="p2", account="Assets:Cash")
    assert validate_postings([p1, blank]) == []


# --- Defect 3: struct_key must reflect whether a leg carries an amount ---

def test_struct_key_changes_when_leg_flips_to_blank():
    """Flipping a leg from amount-bearing to blank changes struct_key."""
    amount_leg = _amount_leg(id="p1", account="Assets:Cash", amount="10.00", currency="USD")
    blank_leg = Posting(id="p1", account="Assets:Cash")  # same account/currency, no amount
    assert struct_key(amount_leg) != struct_key(blank_leg)


def test_struct_key_stable_under_amount_value_change():
    """Changing only the amount value must NOT change struct_key (overrides survive)."""
    a = _amount_leg(amount="15.00")
    b = _amount_leg(amount="99.00")
    assert struct_key(a) == struct_key(b)
