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


def amortize(terms: LoanTerms, events: list[Event] | None = None) -> list[Installment]:
    validate_terms(terms)
    r = monthly_rate(terms.annual_rate, terms.interval_months)
    balance = money(terms.principal)
    rows: list[Installment] = []

    if terms.method == "equal_payment":
        payment = equal_payment_amount(terms.principal, r, terms.term_count)
        scheduled = lambda bal: payment                      # noqa: E731
    else:
        per_principal = money(terms.principal / terms.term_count)
        scheduled = lambda bal: money(bal * r) + per_principal  # noqa: E731

    seq = 1
    while balance > 0 and seq <= terms.term_count:
        interest = money(balance * r)
        if terms.method == "equal_payment":
            principal = scheduled(balance) - interest
        else:
            principal = per_principal
        # Final row (fits in one payment) or hard cap: absorb the residual.
        if balance <= principal or seq == terms.term_count:
            principal = balance
        principal = money(principal)
        balance = money(balance - principal)
        rows.append(Installment(
            seq=seq, due_date=_due_date(terms.start_date, seq, terms.interval_months),
            principal=principal, interest=interest, payment=money(principal + interest),
            balance_after=balance,
        ))
        seq += 1
    return rows


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
