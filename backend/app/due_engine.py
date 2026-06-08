import datetime
from typing import Optional

from dateutil.relativedelta import relativedelta


def _unit_delta(interval_unit: str, n: int) -> relativedelta:
    if interval_unit == "day":
        return relativedelta(days=n)
    if interval_unit == "week":
        return relativedelta(weeks=n)
    if interval_unit == "month":
        return relativedelta(months=n)
    if interval_unit == "quarter":
        return relativedelta(months=3 * n)
    if interval_unit == "year":
        return relativedelta(years=n)
    raise ValueError(f"unknown interval_unit: {interval_unit}")


def compute_due_dates(
    anchor: datetime.date,
    interval_unit: str,
    interval_count: int,
    horizon: datetime.date,
    end_date: Optional[datetime.date] = None,
    max_count: Optional[int] = None,
) -> list[datetime.date]:
    """Occurrence dates from anchor up to horizon (inclusive).

    Each occurrence is anchor + i * (interval_unit * interval_count), so month-end
    days clamp relative to the anchor (Jan 31 -> Feb 28) without drifting.
    Terminates at the first of: date > horizon, date > end_date, count >= max_count.
    """
    dates: list[datetime.date] = []
    i = 0
    while True:
        if max_count is not None and i >= max_count:
            break
        d = anchor + _unit_delta(interval_unit, interval_count * i)
        if d > horizon:
            break
        if end_date is not None and d > end_date:
            break
        dates.append(d)
        i += 1
    return dates
