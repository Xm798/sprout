import datetime
from pathlib import Path

import sqlmodel

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


def _first_occ(session, sch):
    return session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).first()


def test_preview_renders_expected_text(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    text = services.build_preview(session, occ.id)
    assert '"Spotify" "sub" #sprout' in text
    assert f'sprout-id: "{occ.sprout_id}"' in text
    assert "Expenses:Subscription  15.00 USD" in text
    assert "Assets:CreditCard\n" in text


def test_preview_applies_per_leg_override(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"main": "9.99"}
    session.add(occ)
    session.commit()
    text = services.build_preview(session, occ.id)
    assert "Expenses:Subscription  9.99 USD" in text


def test_confirm_with_override_amounts(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    services.confirm_occurrence(session, config, occ.id, override_amounts={"main": "9.99"})
    written = Path(config.ledger_root, "sprout.bean").read_text()
    assert "9.99 USD" in written
    session.refresh(occ)
    assert occ.override_amounts == {"main": "9.99"}


def test_confirm_writes_and_marks(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    result = services.confirm_occurrence(session, config, occ.id)
    assert result.status == "confirmed"
    written = Path(result.written_path).read_text()
    assert occ.sprout_id in written
    assert "Expenses:Subscription" in written


def test_skip_marks_skipped(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    result = services.skip_occurrence(session, occ.id)
    assert result.status == "skipped"


def test_confirm_is_idempotent_no_duplicate(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    services.confirm_occurrence(session, config, occ.id)
    services.confirm_occurrence(session, config, occ.id)
    written = Path(config.ledger_root, "sprout.bean").read_text()
    assert written.count(occ.sprout_id) == 1


def test_update_schedule_preserves_overrides_on_narration_edit(session, config, today):
    from app.models import ScheduleCreate
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"main": "9.99"}
    session.add(occ)
    session.commit()

    payload = ScheduleCreate(
        name="Spotify", narration="new memo", postings=_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout",
    )
    services.update_schedule(session, sch.id, payload)

    session.refresh(occ)
    assert occ.override_amounts == {"main": "9.99"}


def test_update_schedule_clears_override_when_posting_account_changes(session, config, today):
    from app.models import ScheduleCreate
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"main": "9.99"}
    session.add(occ)
    session.commit()

    changed = _postings()
    changed[0]["account"] = "Expenses:Music"  # same id "main", different structure
    payload = ScheduleCreate(
        name="Spotify", narration="sub", postings=changed,
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout",
    )
    services.update_schedule(session, sch.id, payload)

    session.refresh(occ)
    assert occ.override_amounts == {}


def test_update_schedule_partial_clear_keeps_unrelated_override(session, config, today):
    from app.models import ScheduleCreate
    three = [
        {"id": "main", "account": "Expenses:Subscription", "amount": "15.00", "currency": "USD", "cost": None, "price": None},
        {"id": "extra", "account": "Expenses:Fees", "amount": "2.00", "currency": "USD", "cost": None, "price": None},
        {"id": "bal", "account": "Assets:CreditCard", "amount": None, "currency": None, "cost": None, "price": None},
    ]
    sch = Schedule(name="Spotify", narration="sub", postings=three, interval_unit="month",
                   interval_count=1, anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout")
    session.add(sch); session.commit(); session.refresh(sch)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"main": "9.99", "extra": "3.00"}
    session.add(occ); session.commit()

    changed = [dict(p) for p in three]
    changed[1]["account"] = "Expenses:OtherFees"  # structural change to "extra" only
    payload = ScheduleCreate(name="Spotify", narration="sub", postings=changed, interval_unit="month",
                             interval_count=1, anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout")
    services.update_schedule(session, sch.id, payload)
    session.refresh(occ)
    assert occ.override_amounts == {"main": "9.99"}  # extra cleared, main kept


def test_tags_with_spaces_render_cleanly(session, config, today):
    sch = Schedule(
        name="Spotify", narration="sub", postings=_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6,
        tags="a, b",
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    text = services.build_preview(session, occ.id)
    assert "#a #b" in text
    assert "# b" not in text


def test_update_schedule_clears_override_when_leg_flips_amount_to_blank(session, config, today):
    """Flipping a leg from amount-bearing to blank (same account/currency) must prune its override."""
    from app.models import ScheduleCreate
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"main": "9.99"}
    session.add(occ)
    session.commit()

    # Flip "main" from amount-leg to blank auto-balance leg; keep "bal" as amount-leg
    flipped = [
        {"id": "main", "account": "Expenses:Subscription", "amount": None,
         "currency": None, "cost": None, "price": None},
        {"id": "bal", "account": "Assets:CreditCard", "amount": "15.00",
         "currency": "USD", "cost": None, "price": None},
    ]
    payload = ScheduleCreate(
        name="Spotify", narration="sub", postings=flipped,
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout",
    )
    services.update_schedule(session, sch.id, payload)

    session.refresh(occ)
    # Override for "main" must be pruned because the leg is now blank
    assert occ.override_amounts == {}


def test_update_schedule_clears_override_for_deleted_posting(session, config, today):
    from app.models import ScheduleCreate
    three = [
        {"id": "main", "account": "Expenses:Subscription", "amount": "15.00", "currency": "USD", "cost": None, "price": None},
        {"id": "extra", "account": "Expenses:Fees", "amount": "2.00", "currency": "USD", "cost": None, "price": None},
        {"id": "bal", "account": "Assets:CreditCard", "amount": None, "currency": None, "cost": None, "price": None},
    ]
    sch = Schedule(name="Spotify", narration="sub", postings=three, interval_unit="month",
                   interval_count=1, anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout")
    session.add(sch); session.commit(); session.refresh(sch)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"main": "9.99", "extra": "3.00"}
    session.add(occ); session.commit()

    without_extra = [three[0], three[2]]  # drop "extra" entirely
    payload = ScheduleCreate(name="Spotify", narration="sub", postings=without_extra, interval_unit="month",
                             interval_count=1, anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout")
    services.update_schedule(session, sch.id, payload)
    session.refresh(occ)
    assert occ.override_amounts == {"main": "9.99"}  # deleted posting's override cleared


# ── override-key validation ────────────────────────────────────────────────────

def test_confirm_unknown_override_key_raises_422(session, config, today):
    """Unknown posting id in override_amounts must raise ValueError, leave occ pending,
    leave the ledger file unwritten, and NOT persist the bogus key."""
    import pytest
    from pathlib import Path
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)

    with pytest.raises(ValueError, match="bogus"):
        services.confirm_occurrence(session, config, occ.id, override_amounts={"bogus": "99.00"})

    session.refresh(occ)
    assert occ.status == "pending"
    ledger = Path(config.ledger_root, "sprout.bean")
    assert not ledger.exists()
    assert "bogus" not in (occ.override_amounts or {})


def test_confirm_malformed_amount_friendly_message(session, config, today):
    """confirm with a non-numeric amount must raise ValueError with the friendly
    'is not a number' message (not a raw decimal exception)."""
    import pytest
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)

    with pytest.raises(ValueError, match="is not a number"):
        services.confirm_occurrence(session, config, occ.id, override_amounts={"main": "abc"})


def test_preview_unknown_override_key_raises(session, config, today):
    """build_preview with an unknown posting id in override_amounts must raise ValueError."""
    import pytest
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)

    with pytest.raises(ValueError, match="bogus"):
        services.build_preview(session, occ.id, override_amounts={"bogus": "99.00"})


def test_preview_stale_stored_override_key_raises(session, config, today):
    """build_preview must validate the STORED occ.override_amounts too — a stale
    key (legacy data or orphaned by a schedule edit) must raise, even with no
    transient overrides passed (GET preview path)."""
    import pytest
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"stale": "99.00"}
    session.add(occ)
    session.commit()

    with pytest.raises(ValueError, match="stale"):
        services.build_preview(session, occ.id)


def test_preview_malformed_amount_friendly_message(session, config, today):
    """build_preview with a non-numeric amount must raise ValueError with the friendly message."""
    import pytest
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)

    with pytest.raises(ValueError, match="is not a number"):
        services.build_preview(session, occ.id, override_amounts={"main": "abc"})
