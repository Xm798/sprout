import datetime

import pytest

from app.bean_format import format_transaction, apply_beanfmt
from app.postings import Posting, Cost, Price


def test_two_leg_with_tag_and_meta():
    text = format_transaction(
        date=datetime.date(2026, 6, 15),
        payee="Spotify",
        narration="subscription",
        postings=[
            Posting(id="a", account="Expenses:Subscription", amount="15.00", currency="USD"),
            Posting(id="b", account="Assets:CreditCard"),
        ],
        tags=["sprout"],
        meta={"sprout-id": "sch1-20260615"},
    )
    assert text == (
        '2026-06-15 * "Spotify" "subscription" #sprout\n'
        '  sprout-id: "sch1-20260615"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )


def test_integer_amount_renders_bare():
    text = format_transaction(
        date=datetime.date(2026, 6, 1),
        payee="Rent",
        narration="",
        postings=[
            Posting(id="a", account="Expenses:Housing:Rent", amount="1200", currency="USD"),
            Posting(id="b", account="Assets:Bank:Checking"),
        ],
    )
    assert text == (
        '2026-06-01 * "Rent" ""\n'
        "  Expenses:Housing:Rent  1200 USD\n"
        "  Assets:Bank:Checking\n"
    )


def test_cost_and_price_render_order():
    text = format_transaction(
        date=datetime.date(2026, 6, 1),
        payee="Broker",
        narration="buy",
        postings=[
            Posting(
                id="a", account="Assets:Stock", amount="10", currency="ACME",
                cost=Cost(amount="100.00", currency="USD"),
                price=Price(amount="105.00", currency="USD"),
            ),
            Posting(id="b", account="Assets:Cash"),
        ],
    )
    assert text == (
        '2026-06-01 * "Broker" "buy"\n'
        "  Assets:Stock  10 ACME {100.00 USD} @ 105.00 USD\n"
        "  Assets:Cash\n"
    )


def test_total_cost_and_total_price():
    text = format_transaction(
        date=datetime.date(2026, 6, 1),
        payee="FX",
        narration="",
        postings=[
            Posting(
                id="a", account="Assets:EUR", amount="100", currency="EUR",
                price=Price(amount="110.00", currency="USD", total=True),
            ),
            Posting(
                id="b", account="Assets:Lot", amount="5", currency="ACME",
                cost=Cost(amount="500.00", currency="USD", total=True),
            ),
            Posting(id="c", account="Assets:Cash"),
        ],
    )
    assert text == (
        '2026-06-01 * "FX" ""\n'
        "  Assets:EUR  100 EUR @@ 110.00 USD\n"
        "  Assets:Lot  5 ACME {{500.00 USD}}\n"
        "  Assets:Cash\n"
    )


# ── apply_beanfmt ──────────────────────────────────────────────────────────────

_SAMPLE = (
    '2026-06-15 * "Spotify" "subscription" #sprout\n'
    '  sprout-id: "sch1-20260615"\n'
    "  Expenses:Subscription  15.00 USD\n"
    "  Assets:CreditCard\n"
)


# All three "no config available" paths — workspace without a config file,
# no workspace at all, nonexistent directory — must format with defaults.
@pytest.mark.parametrize("workspace", ["empty-dir", "none", "missing-dir"])
def test_apply_beanfmt_defaults_without_config(tmp_path, workspace):
    ws = {"empty-dir": tmp_path, "none": None, "missing-dir": tmp_path / "nope"}[workspace]
    text = apply_beanfmt(_SAMPLE, ws)
    # beanfmt defaults: 4-space indent, meta and sprout-id line preserved
    assert "    Expenses:Subscription" in text
    assert 'sprout-id: "sch1-20260615"' in text
    assert text.endswith("\n")


def test_apply_beanfmt_loads_workspace_config(tmp_path):
    (tmp_path / ".beanfmt.toml").write_text("indent = 6\n")
    text = apply_beanfmt(_SAMPLE, tmp_path)
    assert "      Expenses:Subscription" in text
    assert '      sprout-id: "sch1-20260615"' in text


def test_apply_beanfmt_invalid_config_returns_input_unchanged(tmp_path):
    (tmp_path / ".beanfmt.toml").write_text("indent = [broken\n")
    assert apply_beanfmt(_SAMPLE, tmp_path) == _SAMPLE
