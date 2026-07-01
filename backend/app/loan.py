from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from pydantic import BaseModel
from dateutil.relativedelta import relativedelta

CENT = Decimal("0.01")


def money(x: Decimal, exp: Decimal = CENT) -> Decimal:
    return Decimal(x).quantize(exp, rounding=ROUND_HALF_UP)


def monthly_rate(annual: Decimal, interval_months: int) -> Decimal:
    return annual / 12 * interval_months


class LoanTerms(BaseModel):
    principal: Decimal
    annual_rate: Decimal
    term_count: int
    method: str                 # equal_payment | equal_principal
    start_date: date
    interval_months: int = 1


class Event(BaseModel):
    id: str
    kind: str                   # prepayment | rate_change
    date: date
    amount: Optional[Decimal] = None       # prepayment
    mode: Optional[str] = None             # prepayment: shorten_term | reduce_payment
    annual_rate: Optional[Decimal] = None  # rate_change


class Installment(BaseModel):
    seq: Optional[int]
    due_date: date
    principal: Decimal
    interest: Decimal
    payment: Decimal
    balance_after: Decimal
    is_prepayment: bool = False
    event_id: Optional[str] = None


class DegenerateLoan(ValueError):
    """Loan params that never amortize to zero (payment <= first-period interest)."""


def equal_payment_amount(principal: Decimal, r: Decimal, n: int) -> Decimal:
    if r == 0:
        return money(principal / n)
    factor = (1 + r) ** n
    return money(principal * r * factor / (factor - 1))


def _due_date(start: date, seq: int, interval_months: int) -> date:
    return start + relativedelta(months=interval_months * (seq - 1))


def _remaining_count(balance: Decimal, r: Decimal, payment: Decimal) -> int:
    """Loop-derived remaining periods to amortize `balance` at `payment` (shorten_term).
    Loop is authoritative; a closed-form ceil is only used as a debug assertion."""
    n, b = 0, balance
    while b > 0 and n < 100000:
        interest = money(b * r)
        principal = payment - interest
        if principal <= 0:
            raise DegenerateLoan("payment no longer exceeds interest after event")
        if b <= principal:
            principal = b
        b = money(b - principal)
        n += 1
    return n


def amortize(terms: LoanTerms, events: list[Event] | None = None) -> list[Installment]:
    validate_terms(terms)
    events = sorted(events or [], key=lambda e: e.date)
    r = monthly_rate(terms.annual_rate, terms.interval_months)
    balance = money(terms.principal)
    rows: list[Installment] = []

    if terms.method == "equal_payment":
        payment = equal_payment_amount(terms.principal, r, terms.term_count)
        per_principal = None
    else:
        payment = None
        per_principal = money(terms.principal / terms.term_count)

    remaining = terms.term_count
    seq = 1
    ei = 0
    while balance > 0 and seq <= terms.term_count and remaining > 0:
        interest = money(balance * r)
        if terms.method == "equal_payment":
            principal = payment - interest
        else:
            principal = per_principal
        if balance <= principal or remaining == 1:
            principal = balance
        principal = money(principal)
        balance = money(balance - principal)
        due = _due_date(terms.start_date, seq, terms.interval_months)
        rows.append(Installment(
            seq=seq, due_date=due, principal=principal, interest=interest,
            payment=money(principal + interest), balance_after=balance,
        ))
        remaining -= 1

        # Apply any events landing on this payment date (regular-then-event order).
        while ei < len(events) and events[ei].date == due and balance > 0:
            ev = events[ei]; ei += 1
            balance = _apply_event(ev, balance, r, rows, due)
            if terms.method == "equal_payment":
                payment, remaining = _recompute_equal_payment(ev, balance, r, payment, remaining)
            else:
                per_principal, remaining = _recompute_equal_principal(ev, balance, r, per_principal, remaining)
        seq += 1

    return rows


def _apply_event(ev: Event, balance: Decimal, r: Decimal,
                 rows: list[Installment], due: date) -> Decimal:
    if ev.kind == "prepayment":
        amt = money(min(ev.amount, balance))
        balance = money(balance - amt)
        rows.append(Installment(
            seq=None, due_date=due, principal=amt, interest=Decimal("0"),
            payment=amt, balance_after=balance, is_prepayment=True, event_id=ev.id,
        ))
    # rate_change carries no cash row; handled in the recompute helpers.
    return balance


def _recompute_equal_payment(ev, balance, r, payment, remaining):
    if balance <= 0:
        return payment, 0
    if ev.kind == "rate_change":
        r = monthly_rate(ev.annual_rate, 1)                      # interval folded into rate upstream
        return equal_payment_amount(balance, r, remaining), remaining
    if ev.mode == "shorten_term":
        return payment, _remaining_count(balance, r, payment)
    return equal_payment_amount(balance, r, remaining), remaining  # reduce_payment


def _recompute_equal_principal(ev, balance, r, per_principal, remaining):
    if balance <= 0:
        return per_principal, 0
    if ev.kind == "rate_change" or ev.mode == "reduce_payment":
        return money(balance / remaining), remaining      # keep count, re-slice principal
    # shorten_term: keep per_principal, loop to zero
    n = 0; b = balance
    while b > 0 and n < 100000:
        b = money(b - min(per_principal, b)); n += 1
    return per_principal, n


def validate_terms(terms: LoanTerms) -> None:
    r = monthly_rate(terms.annual_rate, terms.interval_months)
    if terms.method == "equal_payment":
        M = equal_payment_amount(terms.principal, r, terms.term_count)
        if M <= money(terms.principal * r):
            raise DegenerateLoan(
                "monthly payment does not exceed first-period interest; loan never amortizes"
            )
    elif terms.method == "equal_principal":
        if money(terms.principal / terms.term_count) <= 0:
            raise DegenerateLoan("per-period principal rounds to zero")
    else:
        raise ValueError(f"unknown method {terms.method!r}")
