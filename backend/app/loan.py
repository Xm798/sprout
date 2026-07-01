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
