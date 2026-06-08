import datetime

from app.due_engine import compute_due_dates

D = datetime.date


def test_monthly_basic():
    dates = compute_due_dates(
        anchor=D(2026, 1, 15), interval_unit="month", interval_count=1,
        horizon=D(2026, 4, 15),
    )
    assert dates == [D(2026, 1, 15), D(2026, 2, 15), D(2026, 3, 15), D(2026, 4, 15)]


def test_horizon_excludes_future():
    dates = compute_due_dates(
        anchor=D(2026, 1, 15), interval_unit="month", interval_count=1,
        horizon=D(2026, 3, 1),
    )
    assert dates == [D(2026, 1, 15), D(2026, 2, 15)]


def test_interval_count_every_two_weeks():
    dates = compute_due_dates(
        anchor=D(2026, 1, 1), interval_unit="week", interval_count=2,
        horizon=D(2026, 2, 1),
    )
    assert dates == [D(2026, 1, 1), D(2026, 1, 15), D(2026, 1, 29)]


def test_end_date_terminates():
    dates = compute_due_dates(
        anchor=D(2026, 1, 15), interval_unit="month", interval_count=1,
        horizon=D(2026, 12, 31), end_date=D(2026, 3, 20),
    )
    assert dates == [D(2026, 1, 15), D(2026, 2, 15), D(2026, 3, 15)]


def test_max_count_terminates():
    dates = compute_due_dates(
        anchor=D(2026, 1, 15), interval_unit="month", interval_count=1,
        horizon=D(2026, 12, 31), max_count=3,
    )
    assert dates == [D(2026, 1, 15), D(2026, 2, 15), D(2026, 3, 15)]


def test_month_end_clamps():
    dates = compute_due_dates(
        anchor=D(2026, 1, 31), interval_unit="month", interval_count=1,
        horizon=D(2026, 3, 31),
    )
    assert dates == [D(2026, 1, 31), D(2026, 2, 28), D(2026, 3, 31)]


def test_quarter_and_year():
    q = compute_due_dates(D(2026, 1, 1), "quarter", 1, D(2026, 12, 31))
    assert q == [D(2026, 1, 1), D(2026, 4, 1), D(2026, 7, 1), D(2026, 10, 1)]
    y = compute_due_dates(D(2026, 1, 1), "year", 1, D(2028, 6, 1))
    assert y == [D(2026, 1, 1), D(2027, 1, 1), D(2028, 1, 1)]


def test_anchor_after_horizon_is_empty():
    assert compute_due_dates(D(2027, 1, 1), "month", 1, D(2026, 6, 1)) == []
