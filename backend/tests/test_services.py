import datetime
from pathlib import Path

from app.models import Schedule, Occurrence
from app import services


def _postings():
    return [
        {"id": "main", "account": "Expenses:Subscription", "amount": "15.00",
         "currency": "USD", "cost": None, "price": None},
        {"id": "bal", "account": "Assets:CreditCard", "amount": None,
         "currency": None, "cost": None, "price": None},
    ]


def _make_schedule(session):
    sch = Schedule(
        name="Spotify", narration="sub", postings=_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout",
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)
    return sch


def test_schedule_and_occurrence_persist(session):
    sch = _make_schedule(session)
    assert sch.id is not None
    assert sch.postings[0]["account"] == "Expenses:Subscription"

    occ = Occurrence(
        schedule_id=sch.id, due_date=datetime.date(2026, 6, 15),
        sprout_id=f"sch{sch.id}-20260615", override_amounts={"main": "9.99"},
    )
    session.add(occ)
    session.commit()
    session.refresh(occ)
    assert occ.override_amounts == {"main": "9.99"}


def test_materialize_is_idempotent(session, config, today):
    _make_schedule(session)
    created_first = services.materialize_occurrences(session, config, today)
    created_second = services.materialize_occurrences(session, config, today)
    # today is 2026-06-08, so Jun 15 is excluded by horizon -> 5 occurrences
    assert created_first == 5
    assert created_second == 0


def test_preview_renders_expected_text(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = session.exec(
        __import__("sqlmodel").select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).first()
    text = services.build_preview(session, occ.id)
    assert '"Spotify" "sub" #sprout' in text
    assert f'sprout-id: "{occ.sprout_id}"' in text
    assert "Expenses:Subscription  15.00 USD" in text
    assert "Assets:CreditCard\n" in text


def test_confirm_writes_and_marks(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = session.exec(
        __import__("sqlmodel").select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).first()
    result = services.confirm_occurrence(session, config, occ.id)
    assert result.status == "confirmed"
    assert result.written_path is not None
    written = Path(result.written_path).read_text()
    assert occ.sprout_id in written
    assert "Expenses:Subscription" in written


def test_confirm_with_amount_override(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = session.exec(
        __import__("sqlmodel").select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).first()
    services.confirm_occurrence(session, config, occ.id, override_amount=Decimal("9.99"))
    written = Path(config.ledger_root, "sprout.bean").read_text()
    assert "9.99 USD" in written


def test_skip_marks_skipped(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = session.exec(
        __import__("sqlmodel").select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).first()
    result = services.skip_occurrence(session, occ.id)
    assert result.status == "skipped"


def test_confirm_is_idempotent_no_duplicate(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = session.exec(
        __import__("sqlmodel").select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).first()
    services.confirm_occurrence(session, config, occ.id)
    services.confirm_occurrence(session, config, occ.id)
    written = Path(config.ledger_root, "sprout.bean").read_text()
    assert written.count(occ.sprout_id) == 1
