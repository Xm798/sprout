import datetime
from decimal import Decimal

import pytest

from app import exchange_rates as ex


def test_is_crypto_recognizes_known_symbols():
    assert ex.is_crypto("BTC") is True
    assert ex.is_crypto("eth") is True  # case-insensitive
    assert ex.is_crypto("HKD") is False
    assert ex.is_crypto("CNY") is False


def test_provider_routes_crypto_to_coingecko_else_frankfurter():
    assert ex.provider_for("HKD", "CNY") == "frankfurter"
    assert ex.provider_for("BTC", "CNY") == "coingecko"
    assert ex.provider_for("CNY", "ETH") == "coingecko"


def test_parse_frankfurter_extracts_quote_rate_and_date():
    payload = {
        "amount": 1.0,
        "base": "HKD",
        "date": "2026-06-25",
        "rates": {"CNY": 0.8673},
    }
    rate, on = ex.parse_frankfurter(payload, "CNY")
    assert rate == Decimal("0.8673")
    assert on == datetime.date(2026, 6, 25)


def test_parse_frankfurter_missing_quote_raises():
    payload = {"base": "HKD", "date": "2026-06-25", "rates": {"USD": 0.13}}
    with pytest.raises(ValueError):
        ex.parse_frankfurter(payload, "CNY")


def test_parse_coingecko_extracts_rate_for_coin_and_quote():
    payload = {"bitcoin": {"cny": 409172, "hkd": 471770}}
    rate = ex.parse_coingecko(payload, "bitcoin", "CNY")
    assert rate == Decimal("409172")


def test_parse_coingecko_missing_pair_raises():
    payload = {"bitcoin": {"usd": 60160}}
    with pytest.raises(ValueError):
        ex.parse_coingecko(payload, "bitcoin", "CNY")


def test_cache_put_then_get_returns_fresh_rate(session):
    now = datetime.datetime(2026, 6, 25, 12, 0, 0)
    on = datetime.date(2026, 6, 25)
    ex.cache_put(session, "HKD", "CNY", on, "frankfurter", Decimal("0.8673"), now)
    got = ex.cache_get(session, "HKD", "CNY", on, "frankfurter", now)
    assert got == Decimal("0.8673")


def test_cache_get_returns_none_when_stale(session):
    fetched = datetime.datetime(2026, 6, 25, 12, 0, 0)
    on = datetime.date(2026, 6, 25)
    ex.cache_put(session, "HKD", "CNY", on, "frankfurter", Decimal("0.8673"), fetched)
    # A day later the fiat entry has aged past its TTL.
    later = fetched + datetime.timedelta(days=1)
    assert ex.cache_get(session, "HKD", "CNY", on, "frankfurter", later) is None


def test_crypto_cache_expires_faster_than_fiat(session):
    fetched = datetime.datetime(2026, 6, 25, 12, 0, 0)
    on = datetime.date(2026, 6, 25)
    ex.cache_put(session, "BTC", "CNY", on, "coingecko", Decimal("409172"), fetched)
    # Ten minutes later a crypto rate is already stale.
    later = fetched + datetime.timedelta(minutes=10)
    assert ex.cache_get(session, "BTC", "CNY", on, "coingecko", later) is None


def test_get_rate_fetches_on_miss_and_caches(session):
    calls = []

    def fake_fetch(source, base, quote, on):
        calls.append((source, base, quote, on))
        return Decimal("0.8673"), datetime.date(2026, 6, 25)

    now = datetime.datetime(2026, 6, 25, 12, 0, 0)
    q = ex.get_rate(session, "HKD", "CNY", datetime.date(2026, 6, 25),
                    now=now, fetch=fake_fetch)
    assert q.rate == "0.8673"
    assert q.source == "frankfurter"
    assert q.cached is False
    assert q.as_of == datetime.date(2026, 6, 25)
    assert len(calls) == 1


def test_get_rate_hits_cache_without_fetching(session):
    calls = []

    def fake_fetch(source, base, quote, on):
        calls.append(1)
        return Decimal("0.8673"), datetime.date(2026, 6, 25)

    now = datetime.datetime(2026, 6, 25, 12, 0, 0)
    on = datetime.date(2026, 6, 25)
    ex.get_rate(session, "HKD", "CNY", on, now=now, fetch=fake_fetch)
    second = ex.get_rate(session, "HKD", "CNY", on, now=now, fetch=fake_fetch)
    assert second.cached is True
    assert second.rate == "0.8673"
    assert len(calls) == 1  # network hit only once


def test_get_rate_normalizes_currency_case(session):
    def fake_fetch(source, base, quote, on):
        assert base == "HKD" and quote == "CNY"  # upper-cased before fetch
        return Decimal("0.8673"), on

    now = datetime.datetime(2026, 6, 25, 12, 0, 0)
    q = ex.get_rate(session, "hkd", "cny", datetime.date(2026, 6, 25),
                    now=now, fetch=fake_fetch)
    assert q.base == "HKD" and q.quote == "CNY"


def test_coingecko_plan_crypto_base_queries_coin_in_fiat():
    coin_id, vs, invert = ex.coingecko_plan("BTC", "CNY")
    assert coin_id == "bitcoin"
    assert vs == "CNY"
    assert invert is False


def test_coingecko_plan_crypto_quote_inverts():
    # CNY->BTC wants BTC-per-CNY, but CoinGecko only prices BTC in CNY, so invert.
    coin_id, vs, invert = ex.coingecko_plan("CNY", "BTC")
    assert coin_id == "bitcoin"
    assert vs == "CNY"
    assert invert is True


def test_coingecko_plan_crypto_to_crypto_uses_quote_as_vs():
    coin_id, vs, invert = ex.coingecko_plan("BTC", "ETH")
    assert coin_id == "bitcoin"
    assert vs == "ETH"
    assert invert is False


def test_cache_put_overwrites_existing_entry(session):
    on = datetime.date(2026, 6, 25)
    t1 = datetime.datetime(2026, 6, 25, 12, 0, 0)
    ex.cache_put(session, "BTC", "CNY", on, "coingecko", Decimal("409172"), t1)
    t2 = t1 + datetime.timedelta(minutes=1)
    ex.cache_put(session, "BTC", "CNY", on, "coingecko", Decimal("410000"), t2)
    assert ex.cache_get(session, "BTC", "CNY", on, "coingecko", t2) == Decimal("410000")
