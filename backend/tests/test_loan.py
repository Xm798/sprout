from decimal import Decimal
from datetime import date
import pytest
from app.loan import LoanTerms, Event, Installment, monthly_rate, money, CENT


def test_money_rounds_half_up_to_cents():
    assert money(Decimal("1.005")) == Decimal("1.01")
    assert money(Decimal("2.344")) == Decimal("2.34")


def test_monthly_rate_divides_annual_by_twelve():
    assert monthly_rate(Decimal("0.0485"), 1) == Decimal("0.0485") / 12
    assert monthly_rate(Decimal("0.06"), 3) == Decimal("0.06") / 12 * 3


def test_loanterms_and_event_validate():
    t = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                  term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    assert t.interval_months == 1
    e = Event(id="e1", kind="prepayment", date=date(2027, 1, 1),
              amount=Decimal("200000"), mode="shorten_term")
    assert e.kind == "prepayment"


def test_equal_payment_amount_golden():
    from app.loan import equal_payment_amount
    # 1,000,000 @ 4.85%/360mo -> raw 5276.9183 -> 5276.92 (spec-corrected golden)
    M = equal_payment_amount(Decimal("1000000"), Decimal("0.0485") / 12, 360)
    assert M == Decimal("5276.92")


def test_equal_payment_zero_rate_is_principal_over_n():
    from app.loan import equal_payment_amount
    assert equal_payment_amount(Decimal("1200"), Decimal("0"), 12) == Decimal("100.00")


def test_validate_terms_rejects_degenerate_equal_payment():
    # payment must exceed first-period interest, else balance never falls
    from app.loan import validate_terms, DegenerateLoan
    bad = LoanTerms(principal=Decimal("100"), annual_rate=Decimal("0.30"),
                    term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    with pytest.raises(DegenerateLoan):
        validate_terms(bad)


def test_validate_terms_rejects_degenerate_equal_principal():
    from app.loan import validate_terms, DegenerateLoan
    bad = LoanTerms(principal=Decimal("1"), annual_rate=Decimal("0.05"),
                    term_count=360, method="equal_principal", start_date=date(2026, 1, 1))
    with pytest.raises(DegenerateLoan):
        validate_terms(bad)
