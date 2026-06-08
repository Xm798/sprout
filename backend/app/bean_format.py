import datetime
from decimal import Decimal
from typing import Optional


def _fmt_amount(amount: Decimal) -> str:
    # Use fixed-point; strip trailing zeros from the fractional part but keep
    # at least 2 decimal places so DB-retrieved Numeric(20,8) values render
    # as e.g. "15.00" rather than "15.00000000".
    s = format(amount, "f")
    if "." in s:
        integer_part, frac_part = s.split(".")
        stripped = frac_part.rstrip("0").ljust(2, "0")
        return f"{integer_part}.{stripped}"
    return s


def format_transaction(
    date: datetime.date,
    payee: str,
    narration: str,
    postings: list[tuple[str, Optional[Decimal], Optional[str]]],
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
    for account, amount, currency in postings:
        if amount is None:
            lines.append(f"  {account}")
        else:
            lines.append(f"  {account}  {_fmt_amount(amount)} {currency}")
    return "\n".join(lines) + "\n"
