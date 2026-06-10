from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import BaseModel


class Cost(BaseModel):
    amount: str          # Decimal serialized as string
    currency: str
    total: bool = False  # True -> {{...}} total cost; False -> {...} per-unit


class Price(BaseModel):
    amount: str          # Decimal serialized as string
    currency: str
    total: bool = False  # True -> @@ total price; False -> @ per-unit


class Posting(BaseModel):
    id: str
    account: str
    amount: Optional[str] = None      # None = auto-balance leg
    currency: Optional[str] = None
    cost: Optional[Cost] = None
    price: Optional[Price] = None


def _is_decimal(s: str) -> bool:
    try:
        return Decimal(s).is_finite()
    except (InvalidOperation, TypeError, ValueError):
        return False


def parse_postings(raw: list[dict]) -> list[Posting]:
    return [Posting.model_validate(d) for d in (raw or [])]


def dump_postings(postings: list[Posting]) -> list[dict]:
    return [p.model_dump() for p in postings]


def validate_postings(postings: list[Posting], *, require_blank_leg: bool = False) -> list[str]:
    errors: list[str] = []
    if len(postings) < 2:
        errors.append("a transaction needs at least 2 postings")
    seen_ids: set[str] = set()
    for p in postings:
        if p.id in seen_ids:
            errors.append(f"duplicate posting id {p.id!r}")
        seen_ids.add(p.id)
    blank = [p for p in postings if p.amount is None]
    amount_legs = [p for p in postings if p.amount is not None]
    if len(blank) > 1:
        errors.append("at most one posting may have a blank amount")
    if not amount_legs:
        errors.append("at least one posting must have an amount")
    for p in amount_legs:
        if not p.currency:
            errors.append(f"{p.account}: an amount requires a currency")
        if p.amount is not None and not _is_decimal(p.amount):
            errors.append(f"{p.account}: amount {p.amount!r} is not a number")
        if p.cost is not None and not _is_decimal(p.cost.amount):
            errors.append(f"{p.account}: cost amount {p.cost.amount!r} is not a number")
        if p.price is not None and not _is_decimal(p.price.amount):
            errors.append(f"{p.account}: price amount {p.price.amount!r} is not a number")
    for p in blank:
        if p.cost is not None or p.price is not None:
            errors.append(f"{p.account}: cost/price requires an amount")
    if require_blank_leg and len(blank) != 1:
        errors.append("a tunable schedule must have exactly one blank (auto-balance) leg")
    return errors


def validate_overrides(postings: list[Posting], overrides: dict) -> list[str]:
    """Return error strings for any override key that has no matching posting id."""
    if not overrides:
        return []
    valid_ids = {p.id for p in postings}
    return [
        f"unknown posting id {pid!r} in override_amounts"
        for pid in overrides
        if pid not in valid_ids
    ]


def headline(postings: list[Posting]) -> tuple[Optional[str], Optional[str]]:
    for p in postings:
        if p.amount is not None:
            return p.amount, p.currency
    return None, None


def struct_key(p: Posting) -> tuple:
    """Identity of a posting's structure, ignoring its amount value — used to decide
    whether an occurrence's override for this posting id is still valid.
    Includes whether the leg carries an amount so that flipping amount↔blank is detected."""
    return (
        p.account,
        p.currency,  # the leg's own commodity, intentionally distinct from cost/price currency
        p.cost.model_dump() if p.cost else None,
        p.price.model_dump() if p.price else None,
        p.amount is not None,  # has-amount boolean; detects amount↔blank flip
    )
