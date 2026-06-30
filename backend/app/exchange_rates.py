"""Exchange-rate fetching for multi-currency postings.

Fiat pairs use the European Central Bank reference rates via Frankfurter
(no key, daily); pairs involving a cryptocurrency use CoinGecko (no key,
minute-level). Fetched rates are cached so the ledger only hits the network
when a value is missing or stale.
"""

import datetime
from decimal import Context, Decimal
from typing import Callable, Optional

import httpx
from pydantic import BaseModel
from sqlmodel import Session

from app.models import RateCacheEntry

FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
COINGECKO_URL = "https://api.coingecko.com/api/v3"
HTTP_TIMEOUT = 10.0


class RateQuote(BaseModel):
    base: str
    quote: str
    rate: str           # Decimal serialized as string, matching posting amounts
    source: str
    as_of: datetime.date  # the date the rate is effective for
    cached: bool


class RateError(Exception):
    """Raised when a rate cannot be fetched (unknown pair, upstream failure)."""

# Cache freshness per source. Frankfurter publishes ECB rates once per business
# day, so a half-day TTL re-fetches the next day's value without hammering it;
# CoinGecko is live, so crypto rates go stale within minutes.
TTL = {
    "frankfurter": datetime.timedelta(hours=12),
    "coingecko": datetime.timedelta(minutes=5),
}

# Crypto symbol -> CoinGecko coin id. Doubles as the set of recognised crypto
# codes, so detection and id-resolution share a single source of truth.
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "SOL": "solana",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "LTC": "litecoin",
}


def _quantize_sig(value: Decimal, sig: int = 12) -> Decimal:
    """Cap a rate to ``sig`` significant figures. Inverting a large crypto price
    (1 / 409172) otherwise yields a 28-digit quotient that beancount renders and
    validates badly; short values pass through unchanged."""
    if value == 0:
        return value
    return Context(prec=sig).create_decimal(value)


def is_crypto(code: str) -> bool:
    return code.upper() in COINGECKO_IDS


def provider_for(base: str, quote: str) -> str:
    if is_crypto(base) or is_crypto(quote):
        return "coingecko"
    return "frankfurter"


def parse_frankfurter(payload: dict, quote: str) -> tuple[Decimal, datetime.date]:
    """Pull the quote rate and the rate's effective date out of a Frankfurter
    ``/latest`` response: {"base":"HKD","date":"2026-06-25","rates":{"CNY":0.8673}}.
    The date is the ECB business day the value belongs to, not today."""
    rates = payload.get("rates") or {}
    if quote.upper() not in rates:
        raise ValueError(f"frankfurter returned no rate for {quote!r}")
    rate = Decimal(str(rates[quote.upper()]))
    on = datetime.date.fromisoformat(payload["date"])
    return rate, on


def parse_coingecko(payload: dict, coin_id: str, quote: str) -> Decimal:
    """Pull the price out of a CoinGecko ``/simple/price`` response keyed by coin
    id and lower-cased quote currency: {"bitcoin":{"cny":409172}}."""
    prices = payload.get(coin_id) or {}
    key = quote.lower()
    if key not in prices:
        raise ValueError(f"coingecko returned no price for {coin_id}/{quote}")
    return Decimal(str(prices[key]))


def coingecko_plan(base: str, quote: str) -> tuple[str, str, bool]:
    """Resolve a base->quote pair to a CoinGecko query plan.

    CoinGecko prices a coin in a vs-currency, so the crypto leg becomes the coin
    and the other leg the vs-currency. When the crypto is the *quote* leg the
    raw price is the wrong way round and must be inverted."""
    if is_crypto(base):
        return COINGECKO_IDS[base], quote, False
    return COINGECKO_IDS[quote], base, True


def cache_get(
    session: Session,
    base: str,
    quote: str,
    on: datetime.date,
    source: str,
    now: datetime.datetime,
) -> RateCacheEntry | None:
    """Return the cached entry if a fresh one exists, else None. Returns the
    whole entry so callers see the stored effective_date alongside the rate."""
    entry = session.get(RateCacheEntry, (base, quote, on, source))
    if entry is None:
        return None
    if now - entry.fetched_at >= TTL[source]:
        return None
    return entry


def cache_put(
    session: Session,
    base: str,
    quote: str,
    on: datetime.date,
    source: str,
    rate: Decimal,
    effective_date: datetime.date,
    now: datetime.datetime,
) -> None:
    """Insert or refresh the cached rate for this (base, quote, date, source)."""
    entry = session.get(RateCacheEntry, (base, quote, on, source))
    if entry is None:
        entry = RateCacheEntry(
            base=base, quote=quote, rate_date=on, source=source,
            rate=str(rate), effective_date=effective_date, fetched_at=now,
        )
    else:
        entry.rate = str(rate)
        entry.effective_date = effective_date
        entry.fetched_at = now
    session.add(entry)
    session.commit()


def _network_fetch(
    source: str,
    base: str,
    quote: str,
    on: datetime.date,
    *,
    transport: Optional[httpx.BaseTransport] = None,
) -> tuple[Decimal, datetime.date]:
    """Hit the upstream provider and return (rate, effective_date).

    Frankfurter is queried for the requested date (it falls back to the most
    recent ECB business day on its own); CoinGecko only serves live prices, so
    the effective date is the requested date. Both upstream failures and
    well-formed responses missing the requested symbol surface as RateError so
    the router can map them to 502 rather than leaking a 500."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, transport=transport) as client:
            if source == "frankfurter":
                resp = client.get(
                    f"{FRANKFURTER_URL}/{on.isoformat()}",
                    params={"base": base, "symbols": quote},
                )
                resp.raise_for_status()
                return parse_frankfurter(resp.json(), quote)
            coin_id, vs, invert = coingecko_plan(base, quote)
            resp = client.get(
                f"{COINGECKO_URL}/simple/price",
                params={"ids": coin_id, "vs_currencies": vs.lower()},
            )
            resp.raise_for_status()
            price = parse_coingecko(resp.json(), coin_id, vs)
            rate = _quantize_sig(Decimal(1) / price) if invert else price
            return rate, on
    except (httpx.HTTPError, ValueError) as exc:
        raise RateError(f"{source} request failed: {exc}") from exc


def get_rate(
    session: Session,
    base: str,
    quote: str,
    on: Optional[datetime.date] = None,
    *,
    now: Optional[datetime.datetime] = None,
    fetch: Optional[Callable[..., tuple[Decimal, datetime.date]]] = None,
) -> RateQuote:
    """Return the rate for base->quote, serving a fresh cache entry when present
    and otherwise fetching from the upstream provider and caching the result."""
    base, quote = base.upper(), quote.upper()
    now = now or datetime.datetime.now()
    on = on or now.date()
    # An identity conversion is always 1; skip the cache and the upstream call
    # (Frankfurter omits the base from its own rates map and would 500 here).
    if base == quote:
        return RateQuote(base=base, quote=quote, rate="1",
                         source="identity", as_of=on, cached=False)
    source = provider_for(base, quote)
    # CoinGecko only serves the current price, so a stale requested date can't be
    # honoured; key the cache and report as_of under today rather than mislabel a
    # live price with a past date.
    if source == "coingecko":
        on = now.date()

    cached = cache_get(session, base, quote, on, source, now)
    if cached is not None:
        return RateQuote(base=base, quote=quote, rate=cached.rate,
                         source=source, as_of=cached.effective_date, cached=True)

    fetch = fetch or _network_fetch
    rate, as_of = fetch(source, base, quote, on)
    cache_put(session, base, quote, on, source, rate, as_of, now)
    return RateQuote(base=base, quote=quote, rate=str(rate),
                     source=source, as_of=as_of, cached=False)
