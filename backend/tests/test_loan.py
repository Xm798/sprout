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


def test_amortize_equal_payment_zeroes_and_sums():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                      term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    rows = amortize(terms)
    assert len(rows) == 360
    assert rows[0].seq == 1 and rows[-1].seq == 360
    assert rows[-1].balance_after == Decimal("0.00")
    assert sum(r.principal for r in rows) == Decimal("1000000.00")
    # interest declines, principal rises across the schedule
    assert rows[0].interest > rows[-1].interest
    assert rows[0].principal < rows[-1].principal


def test_amortize_equal_principal_fixed_principal_declining_interest():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1200000"), annual_rate=Decimal("0.06"),
                      term_count=240, method="equal_principal", start_date=date(2026, 1, 1))
    rows = amortize(terms)
    assert len(rows) == 240
    assert rows[0].principal == rows[1].principal == Decimal("5000.00")  # 1.2M/240
    assert rows[0].interest > rows[-1].interest
    assert rows[-1].balance_after == Decimal("0.00")
    assert sum(r.principal for r in rows) == Decimal("1200000.00")


def test_amortize_realized_length_below_term_count_on_rounding_payoff():
    # fin-rev case: cent-rounding fully amortizes before term_count
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("777.77"), annual_rate=Decimal("0.30"),
                      term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    rows = amortize(terms)
    assert len(rows) < 360
    assert rows[-1].balance_after == Decimal("0.00")


def test_amortize_dates_step_monthly_from_start():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1200"), annual_rate=Decimal("0"),
                      term_count=3, method="equal_payment", start_date=date(2026, 1, 31))
    rows = amortize(terms)
    assert [r.due_date for r in rows] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


def test_prepayment_shorten_term_settles_to_zero_and_shortens():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                      term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    ev = [Event(id="p1", kind="prepayment", date=date(2027, 1, 1),
                amount=Decimal("200000"), mode="shorten_term")]
    rows = amortize(terms, ev)
    pp = [r for r in rows if r.is_prepayment]
    assert len(pp) == 1 and pp[0].interest == Decimal("0") and pp[0].event_id == "p1"
    regular = [r for r in rows if not r.is_prepayment]
    assert len(regular) < 360                       # term shortened
    assert rows[-1].balance_after == Decimal("0.00")


def test_prepayment_reduce_payment_keeps_remaining_count():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                      term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    ev = [Event(id="p1", kind="prepayment", date=date(2027, 1, 1),  # after 12 regular rows
                amount=Decimal("200000"), mode="reduce_payment")]
    rows = amortize(terms, ev)
    regular = [r for r in rows if not r.is_prepayment]
    assert len(regular) == 360                       # count preserved
    # payment drops after the prepayment
    after = [r for r in regular if r.due_date > date(2027, 1, 1)]
    assert after[0].payment < Decimal("5276.92")
    assert rows[-1].balance_after == Decimal("0.00")


def test_prepayment_exceeding_balance_settles_immediately():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("100000"), annual_rate=Decimal("0.05"),
                      term_count=120, method="equal_payment", start_date=date(2026, 1, 1))
    ev = [Event(id="p1", kind="prepayment", date=date(2027, 1, 1),
                amount=Decimal("999999"), mode="shorten_term")]
    rows = amortize(terms, ev)
    assert rows[-1].balance_after == Decimal("0.00")
    assert rows[-1].is_prepayment                    # settled by the prepayment row


def test_rate_change_reprices_and_zeroes():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                      term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    # reset on the 25th payment date -> 5.60%
    ev = [Event(id="r1", kind="rate_change", date=date(2028, 1, 1), annual_rate=Decimal("0.0560"))]
    rows = amortize(terms, ev)
    regular = [r for r in rows if not r.is_prepayment]
    assert len(regular) == 360
    assert rows[-1].balance_after == Decimal("0.00")
    before = [r for r in regular if r.due_date < date(2028, 1, 1)][-1]
    reset = [r for r in regular if r.due_date == date(2028, 1, 1)][0]
    # The reset-date row still uses the OLD rate (interest accrued over the prior month);
    # the new rate takes effect on the NEXT period.
    nxt = [r for r in regular if r.due_date > date(2028, 1, 1)][0]
    assert nxt.payment > before.payment              # higher rate -> higher payment

    # Pin the repricing boundary so a wrong convention (new rate on the reset row,
    # or old rate lingering afterwards) is caught, not just the coarse inequality.
    old_r = Decimal("0.0485") / 12
    new_r = Decimal("0.0560") / 12
    # Reset row: interest is OLD rate on the pre-reset balance; payment unchanged.
    assert reset.interest == money(before.balance_after * old_r)
    assert reset.interest == Decimal("3916.11")
    assert reset.payment == before.payment
    # Following row: NEW rate over the full period on the post-reset balance.
    assert nxt.interest == money(reset.balance_after * new_r)
    assert nxt.interest == Decimal("4515.34")


def test_stacked_rate_changes_zero_out():
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                      term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    ev = [Event(id="r1", kind="rate_change", date=date(2028, 1, 1), annual_rate=Decimal("0.0560")),
          Event(id="r2", kind="rate_change", date=date(2029, 1, 1), annual_rate=Decimal("0.0390"))]
    rows = amortize(terms, ev)
    assert rows[-1].balance_after == Decimal("0.00")


def test_rate_change_hitting_degenerate_is_rejected():
    from app.loan import amortize, DegenerateLoan
    terms = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                      term_count=360, method="equal_payment", start_date=date(2026, 1, 1))
    # absurd reset that makes payment <= interest on the remaining balance
    ev = [Event(id="r1", kind="rate_change", date=date(2027, 1, 1), annual_rate=Decimal("5.0"))]
    with pytest.raises(DegenerateLoan):
        amortize(terms, ev)


@pytest.mark.parametrize("method", ["equal_payment", "equal_principal"])
def test_prepayment_interest_charged_on_pre_event_balance(method):
    """A same-date prepayment must NOT lower the regular installment's interest,
    under either amortization method."""
    from app.loan import amortize
    terms = LoanTerms(principal=Decimal("1000000"), annual_rate=Decimal("0.0485"),
                      term_count=360, method=method, start_date=date(2026, 1, 1))
    D = date(2027, 1, 1)  # 13th payment date — a real payment date
    ev = [Event(id="p1", kind="prepayment", date=D,
                amount=Decimal("200000"), mode="shorten_term")]
    rows_no_event = amortize(terms)
    rows_with_event = amortize(terms, ev)

    reg_no_ev = [r for r in rows_no_event if not r.is_prepayment and r.due_date == D][0]
    reg_with_ev = [r for r in rows_with_event if not r.is_prepayment and r.due_date == D][0]

    # Interest must be identical: prepayment reduces balance AFTER the regular installment.
    assert reg_no_ev.interest == reg_with_ev.interest
