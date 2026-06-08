import datetime
from decimal import Decimal

from app.models import Schedule, Occurrence


def test_schedule_and_occurrence_persist(session):
    sch = Schedule(
        name="Spotify",
        narration="subscription",
        amount=Decimal("15.00"),
        currency="USD",
        from_account="Assets:CreditCard",
        to_account="Expenses:Subscription",
        interval_unit="month",
        interval_count=1,
        anchor_date=datetime.date(2026, 1, 15),
        tags="sprout",
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)
    assert sch.id is not None
    assert sch.status == "active"

    occ = Occurrence(
        schedule_id=sch.id,
        due_date=datetime.date(2026, 6, 15),
        sprout_id=f"sch{sch.id}-20260615",
    )
    session.add(occ)
    session.commit()
    session.refresh(occ)
    assert occ.id is not None
    assert occ.status == "pending"
    assert occ.sprout_id == f"sch{sch.id}-20260615"
