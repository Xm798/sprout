import datetime
from decimal import Decimal
from typing import Optional

from app.postings import Posting


def _fmt_amount(amount: Decimal) -> str:
    # Fixed-point. When a fractional part exists, strip trailing zeros but keep
    # >=2 decimals so DB Numeric(20,8) values render as "15.00" not "15.00000000".
    # Whole integers render bare ("1200", "10 ACME") per beancount convention —
    # a context-free formatter can't tell a currency from a commodity.
    s = format(amount, "f")
    if "." in s:
        integer_part, frac_part = s.split(".")
        stripped = frac_part.rstrip("0").ljust(2, "0")
        return f"{integer_part}.{stripped}"
    return s


def _render_posting(p: Posting) -> str:
    if p.amount is None:
        return f"  {p.account}"
    if p.currency is None:
        raise ValueError(f"{p.account}: an amount requires a currency")
    line = f"  {p.account}  {_fmt_amount(Decimal(p.amount))} {p.currency}"
    if p.cost is not None:
        open_b, close_b = ("{{", "}}") if p.cost.total else ("{", "}")
        line += f" {open_b}{_fmt_amount(Decimal(p.cost.amount))} {p.cost.currency}{close_b}"
    if p.price is not None:
        op = "@@" if p.price.total else "@"
        line += f" {op} {_fmt_amount(Decimal(p.price.amount))} {p.price.currency}"
    return line


def format_transaction(
    date: datetime.date,
    payee: str,
    narration: str,
    postings: list[Posting],
    tags: Optional[list[str]] = None,
    meta: Optional[dict[str, str]] = None,
    flag: str = "*",
) -> str:
    tags = tags or []
    tag_str = "".join(f" #{t}" for t in tags)
    lines = [f'{date.isoformat()} {flag} "{payee}" "{narration}"{tag_str}']
    if meta:
        for key, value in meta.items():
            lines.append(f'  {key}: "{value}"')
    for p in postings:
        lines.append(_render_posting(p))
    return "\n".join(lines) + "\n"
