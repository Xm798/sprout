import datetime
import re
import uuid
from decimal import Decimal
from typing import Optional

from beancount.core import data
from beancount.core.number import MISSING
from beancount.parser import parser
from pydantic import BaseModel

from app.bean_format import _fmt_amount
from app.postings import Cost, Posting, Price, validate_postings

# Locates the price annotation on a posting's source line. Cost uses {}, never @,
# so the first @/@@ unambiguously marks the price. We re-read it from source
# because beancount normalizes @@ (total) to a per-unit price and drops the
# @@/@ distinction — see 2026-06-18-bean-text-import-design.md.
_PRICE_RE = re.compile(r"(@@?)\s*([-\d.]+)\s+([A-Z][A-Z0-9'._-]*)")


class ParseError(Exception):
    """Raised for un-fixable input: syntax error, zero, or >1 transactions."""


class ParsedTransaction(BaseModel):
    payee: str
    narration: str
    postings: list[Posting]
    tags: str                  # comma-joined, sorted (matches ScheduleBase.tags)
    anchor_date: datetime.date  # FastAPI serializes to an ISO date string
    warnings: list[str] = []


def _map_cost(cost) -> Optional[Cost]:
    if cost is None:
        return None
    # CostSpec routes {{...}} to number_total and {...} to number_per. Lot
    # date/label are intentionally dropped (not representable in Sprout's Cost).
    if cost.number_total is not None:
        number, total = cost.number_total, True
    else:
        number, total = cost.number_per, False
    if number is None:
        return None
    return Cost(amount=_fmt_amount(number), currency=cost.currency, total=total)


def _map_price(posting, lines: list[str]) -> Optional[Price]:
    if posting.price is None:
        return None
    lineno = (posting.meta or {}).get("lineno")
    if lineno and 1 <= lineno <= len(lines):
        m = _PRICE_RE.search(lines[lineno - 1])
        if m:
            return Price(
                amount=_fmt_amount(Decimal(m.group(2))),
                currency=m.group(3),
                total=(m.group(1) == "@@"),
            )
    # Fallback (regex miss): beancount's number is per-unit, correct for @.
    return Price(amount=_fmt_amount(Decimal(posting.price.number)),
                 currency=posting.price.currency, total=False)


def _map_posting(posting, lines: list[str]) -> Posting:
    units = posting.units
    if units is MISSING or units is None:
        return Posting(id=str(uuid.uuid4()), account=posting.account)
    return Posting(
        id=str(uuid.uuid4()),
        account=posting.account,
        # Canonicalize through the renderer's formatter so the stored string
        # equals what bean_format later emits (stable struct_key, clean round-trip).
        amount=_fmt_amount(units.number),
        currency=units.currency,
        cost=_map_cost(posting.cost),
        price=_map_price(posting, lines),
    )


def parse_transaction(text: str) -> ParsedTransaction:
    entries, errors, _ = parser.parse_string(text)
    if errors:
        raise ParseError(errors[0].message)
    txns = [e for e in entries if isinstance(e, data.Transaction)]
    if not txns:
        raise ParseError("no transaction found")
    if len(txns) > 1:
        raise ParseError("paste exactly one transaction")

    txn = txns[0]
    lines = text.splitlines()
    postings = [_map_posting(p, lines) for p in txn.postings]
    return ParsedTransaction(
        # name is Sprout-internal and never parsed; payee + narration round-trip.
        payee=txn.payee or "",
        narration=txn.narration or "",
        postings=postings,
        tags=",".join(sorted(txn.tags)) if txn.tags else "",
        anchor_date=txn.date,
        warnings=validate_postings(postings),
    )
