from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from pydantic import BaseModel

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
