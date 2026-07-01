import datetime
import re
from pathlib import Path

import pytest
import sqlmodel

from app.models import Schedule, Occurrence, ScheduleCreate
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
        name="Spotify", payee="Spotify AB", narration="sub", postings=_postings(),
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
    text = services.build_preview(session, config, occ.id)
    assert '"Spotify AB" "sub" #sprout' in text  # payee + narration; name stays internal
    assert f'sprout-id: "{occ.sprout_id}"' in text
    # beanfmt aligns the amount column, so match whitespace flexibly
    assert re.search(r"Expenses:Subscription\s+15\.00 USD", text)
    assert "Assets:CreditCard\n" in text


def test_preview_applies_per_leg_override(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"main": "9.99"}
    session.add(occ)
    session.commit()
    text = services.build_preview(session, config, occ.id)
    assert re.search(r"Expenses:Subscription\s+9\.99 USD", text)


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
    services.update_schedule(session, config, sch.id, payload, today)

    session.refresh(occ)
    assert occ.override_amounts == {"main": "9.99"}


def test_update_schedule_clears_override_when_posting_account_changes(session, config, today):
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
    services.update_schedule(session, config, sch.id, payload, today)

    session.refresh(occ)
    assert occ.override_amounts == {}


def test_update_schedule_partial_clear_keeps_unrelated_override(session, config, today):
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
    services.update_schedule(session, config, sch.id, payload, today)
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
    text = services.build_preview(session, config, occ.id)
    assert "#a #b" in text
    assert "# b" not in text


def test_update_schedule_clears_override_when_leg_flips_amount_to_blank(session, config, today):
    """Flipping a leg from amount-bearing to blank (same account/currency) must prune its override."""
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
    services.update_schedule(session, config, sch.id, payload, today)

    session.refresh(occ)
    # Override for "main" must be pruned because the leg is now blank
    assert occ.override_amounts == {}


def test_update_schedule_clears_override_for_deleted_posting(session, config, today):
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
    services.update_schedule(session, config, sch.id, payload, today)
    session.refresh(occ)
    assert occ.override_amounts == {"main": "9.99"}  # deleted posting's override cleared


# ── override-key validation ────────────────────────────────────────────────────

def test_confirm_unknown_override_key_raises_422(session, config, today):
    """Unknown posting id in override_amounts must raise ValueError, leave occ pending,
    leave the ledger file unwritten, and NOT persist the bogus key."""
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
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)

    with pytest.raises(ValueError, match="is not a number"):
        services.confirm_occurrence(session, config, occ.id, override_amounts={"main": "abc"})


def test_preview_unknown_override_key_raises(session, config, today):
    """build_preview with an unknown posting id in override_amounts must raise ValueError."""
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)

    with pytest.raises(ValueError, match="bogus"):
        services.build_preview(session, config, occ.id, override_amounts={"bogus": "99.00"})


def test_preview_stale_stored_override_key_raises(session, config, today):
    """build_preview must validate the STORED occ.override_amounts too — a stale
    key (legacy data or orphaned by a schedule edit) must raise, even with no
    transient overrides passed (GET preview path)."""
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    occ.override_amounts = {"stale": "99.00"}
    session.add(occ)
    session.commit()

    with pytest.raises(ValueError, match="stale"):
        services.build_preview(session, config, occ.id)


def test_preview_malformed_amount_friendly_message(session, config, today):
    """build_preview with a non-numeric amount must raise ValueError with the friendly message."""
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)

    with pytest.raises(ValueError, match="is not a number"):
        services.build_preview(session, config, occ.id, override_amounts={"main": "abc"})


# ── override pruning covers skipped occurrences ───────────────────────────────

def test_update_schedule_prunes_stale_override_on_skipped_occurrence(session, config, today):
    """update_schedule must prune stale overrides from SKIPPED occurrences, not just pending."""
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    # Mark the occurrence as skipped and give it an override that will go stale
    occ.override_amounts = {"main": "9.99"}
    occ.status = "skipped"
    session.add(occ)
    session.commit()

    changed = _postings()
    changed[0]["account"] = "Expenses:Music"  # structural change makes override stale
    payload = ScheduleCreate(
        name="Spotify", narration="sub", postings=changed,
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout",
    )
    services.update_schedule(session, config, sch.id, payload, today)

    session.refresh(occ)
    assert occ.override_amounts == {}


def test_update_schedule_confirmed_occurrence_override_untouched(session, config, today):
    """update_schedule must NOT prune overrides from CONFIRMED occurrences (historical record)."""
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occ = _first_occ(session, sch)
    # Simulate a confirmed occurrence with stored override
    occ.override_amounts = {"main": "9.99"}
    occ.status = "confirmed"
    session.add(occ)
    session.commit()

    changed = _postings()
    changed[0]["account"] = "Expenses:Music"  # structural change
    payload = ScheduleCreate(
        name="Spotify", narration="sub", postings=changed,
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout",
    )
    services.update_schedule(session, config, sch.id, payload, today)

    session.refresh(occ)
    # Confirmed occurrence's override must remain intact
    assert occ.override_amounts == {"main": "9.99"}


# ── cascade delete (service level) ─────────────────────────────────────────────

def test_delete_schedule_removes_occurrences_of_all_statuses(session, config, today):
    """delete_schedule must remove occurrence rows of ALL statuses
    (pending, skipped, confirmed) from the DB along with the schedule."""
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occs = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).all()
    assert len(occs) >= 3
    # Cover every status: confirmed history lives in the ledger files,
    # so deleting the row does not destroy ledger data.
    occs[0].status = "pending"
    occs[1].status = "skipped"
    occs[2].status = "confirmed"
    for occ in occs[:3]:
        session.add(occ)
    session.commit()

    services.delete_schedule(session, sch.id)

    assert session.get(Schedule, sch.id) is None
    remaining = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).all()
    assert remaining == []


def test_delete_schedule_missing_raises_lookup_error(session):
    with pytest.raises(LookupError):
        services.delete_schedule(session, 99999)


def test_confirm_writes_to_schedule_target_file(session, tmp_ledger_config, today):
    sch = _make_schedule(session)
    sch.target_file = "subscriptions.bean"
    session.add(sch)
    session.commit()
    services.materialize_occurrences(session, tmp_ledger_config, today)
    occ = _first_occ(session, sch)

    services.confirm_occurrence(session, tmp_ledger_config, occ.id)

    root = Path(tmp_ledger_config.ledger_root)
    target = root / "subscriptions.bean"
    assert '"Spotify AB" "sub"' in target.read_text()  # payee + narration written
    assert not (root / "sprout.bean").exists()  # global file untouched
    session.refresh(occ)
    assert occ.written_path == str(target)
    main_text = Path(tmp_ledger_config.ledger_main_file).read_text()
    assert main_text.count('include "subscriptions.bean"') == 1


def test_second_confirm_does_not_duplicate_include(session, tmp_ledger_config, today):
    sch = _make_schedule(session)
    sch.target_file = "subscriptions.bean"
    session.add(sch)
    session.commit()
    services.materialize_occurrences(session, tmp_ledger_config, today)
    occs = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).all()
    services.confirm_occurrence(session, tmp_ledger_config, occs[0].id)
    services.confirm_occurrence(session, tmp_ledger_config, occs[1].id)
    main_text = Path(tmp_ledger_config.ledger_main_file).read_text()
    assert main_text.count('include "subscriptions.bean"') == 1


def test_confirm_without_target_file_uses_global_strategy(session, tmp_ledger_config, today):
    sch = _make_schedule(session)  # target_file stays None
    before = Path(tmp_ledger_config.ledger_main_file).read_text()
    services.materialize_occurrences(session, tmp_ledger_config, today)
    occ = _first_occ(session, sch)
    services.confirm_occurrence(session, tmp_ledger_config, occ.id)
    session.refresh(occ)
    assert occ.written_path == str(Path(tmp_ledger_config.ledger_root) / "sprout.bean")
    assert Path(tmp_ledger_config.ledger_main_file).read_text() == before  # main untouched


# ── beanfmt formatting ─────────────────────────────────────────────────────────

def test_confirm_writes_beanfmt_formatted_text(session, tmp_ledger_config, today):
    """Written transactions are formatted with beanfmt, honoring the workspace
    .beanfmt.toml next to the main ledger file."""
    (Path(tmp_ledger_config.ledger_main_file).parent / ".beanfmt.toml").write_text("indent = 6\n")
    sch = _make_schedule(session)
    services.materialize_occurrences(session, tmp_ledger_config, today)
    occ = _first_occ(session, sch)

    services.confirm_occurrence(session, tmp_ledger_config, occ.id)

    written = Path(occ.written_path).read_text()
    assert "      Expenses:Subscription" in written  # 6-space indent from config
    assert f'sprout-id: "{occ.sprout_id}"' in written


def test_preview_matches_beanfmt_workspace_config(session, tmp_ledger_config, today):
    (Path(tmp_ledger_config.ledger_main_file).parent / ".beanfmt.toml").write_text("indent = 6\n")
    sch = _make_schedule(session)
    services.materialize_occurrences(session, tmp_ledger_config, today)
    occ = _first_occ(session, sch)
    text = services.build_preview(session, tmp_ledger_config, occ.id)
    assert "      Expenses:Subscription" in text


def test_confirm_rejects_target_file_escaping_root(session, tmp_ledger_config, today):
    sch = _make_schedule(session)
    sch.target_file = "../escape.bean"  # bypassed router validation (e.g. old DB row)
    session.add(sch)
    session.commit()
    services.materialize_occurrences(session, tmp_ledger_config, today)
    occ = _first_occ(session, sch)
    with pytest.raises(ValueError):
        services.confirm_occurrence(session, tmp_ledger_config, occ.id)
    session.refresh(occ)
    assert occ.status == "pending"


def test_update_schedule_deletes_stale_pendings_on_anchor_change(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)

    payload = ScheduleCreate(
        name="Spotify", narration="sub", postings=_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 20), max_count=6, tags="sprout",
    )
    services.update_schedule(session, config, sch.id, payload, today)

    remaining = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).all()
    # Old 15th-of-month pendings are stale under the new rule; the 20th-of-month
    # ones materialize on the next inbox load, not here.
    assert remaining == []


def test_update_schedule_keeps_confirmed_and_skipped_on_anchor_change(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)
    occs = session.exec(
        sqlmodel.select(Occurrence)
        .where(Occurrence.schedule_id == sch.id)
        .order_by(Occurrence.due_date)
    ).all()
    services.confirm_occurrence(session, config, occs[0].id)
    services.skip_occurrence(session, occs[1].id)

    payload = ScheduleCreate(
        name="Spotify", narration="sub", postings=_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 20), max_count=6, tags="sprout",
    )
    services.update_schedule(session, config, sch.id, payload, today)

    remaining = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).all()
    assert sorted(o.status for o in remaining) == ["confirmed", "skipped"]


def test_update_schedule_same_rule_keeps_pendings(session, config, today):
    sch = _make_schedule(session)
    services.materialize_occurrences(session, config, today)

    payload = ScheduleCreate(
        name="Spotify", narration="renamed memo", postings=_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 15), max_count=6, tags="sprout",
    )
    services.update_schedule(session, config, sch.id, payload, today)

    pendings = session.exec(
        sqlmodel.select(Occurrence).where(
            Occurrence.schedule_id == sch.id, Occurrence.status == "pending"
        )
    ).all()
    assert len(pendings) == 5


def test_resolve_postings_fixed_unchanged(session):
    from app.services import resolve_postings
    from app.models import Schedule, Occurrence
    import datetime
    sch = Schedule(name="s", interval_unit="month", interval_count=1,
                   anchor_date=datetime.date(2026, 1, 1),
                   postings=[{"id": "a", "account": "Expenses:X", "amount": "10", "currency": "CNY"},
                             {"id": "b", "account": "Assets:Y", "amount": None, "currency": None}])
    occ = Occurrence(schedule_id=1, due_date=datetime.date(2026, 1, 1))
    legs = resolve_postings(sch, occ)
    assert [p.amount for p in legs] == ["10", None]


def test_resolve_postings_loan_pending_fills_split(session):
    from app.services import resolve_postings
    from app.models import Schedule, Occurrence
    import datetime
    sch = Schedule(name="m", kind="loan", interval_unit="month", interval_count=1,
                   anchor_date=datetime.date(2026, 1, 1),
                   loan={"principal": "1000000", "annual_rate": "0.0485",
                         "term_count": 360, "method": "equal_payment"}, events=[],
                   postings=[{"id": "p", "account": "Liabilities:Loan", "role": "principal", "currency": "CNY"},
                             {"id": "i", "account": "Expenses:Int", "role": "interest", "currency": "CNY"},
                             {"id": "c", "account": "Assets:Bank", "role": "payment", "currency": "CNY"}])
    occ = Occurrence(schedule_id=1, due_date=datetime.date(2026, 1, 1), loan_seq=1, loan_event="regular")
    legs = {p.role: p.amount for p in resolve_postings(sch, occ)}
    assert legs["interest"] == "4041.67"                    # 1,000,000 * 0.0485/12
    assert legs["payment"] == "-5276.92"                    # outflow negative
    assert legs["principal"] == "1235.25"


def test_resolve_postings_loan_confirmed_uses_frozen(session):
    from app.services import resolve_postings
    from app.models import Schedule, Occurrence
    import datetime
    sch = Schedule(name="m", kind="loan", interval_unit="month", interval_count=1,
                   anchor_date=datetime.date(2026, 1, 1),
                   loan={"principal": "1000000", "annual_rate": "0.0485", "term_count": 360,
                         "method": "equal_payment"}, events=[],
                   postings=[{"id": "p", "account": "Liabilities:Loan", "role": "principal", "currency": "CNY"},
                             {"id": "i", "account": "Expenses:Int", "role": "interest", "currency": "CNY"},
                             {"id": "c", "account": "Assets:Bank", "role": "payment", "currency": "CNY"}])
    occ = Occurrence(schedule_id=1, due_date=datetime.date(2026, 1, 1), loan_seq=1,
                     status="confirmed",
                     frozen_postings=[{"id": "p", "account": "Liabilities:Loan", "amount": "1.00", "currency": "CNY", "role": "principal"},
                                      {"id": "i", "account": "Expenses:Int", "amount": "2.00", "currency": "CNY", "role": "interest"},
                                      {"id": "c", "account": "Assets:Bank", "amount": "-3.00", "currency": "CNY", "role": "payment"}])
    legs = {p.role: p.amount for p in resolve_postings(sch, occ)}
    assert legs == {"principal": "1.00", "interest": "2.00", "payment": "-3.00"}


def test_resolve_postings_confirmed_without_frozen_raises(session):
    from app.services import resolve_postings, StaleOccurrence
    from app.models import Schedule, Occurrence
    import datetime
    sch = Schedule(name="m", kind="loan", interval_unit="month", interval_count=1,
                   anchor_date=datetime.date(2026, 1, 1),
                   loan={"principal": "1000000", "annual_rate": "0.0485", "term_count": 360,
                         "method": "equal_payment"}, events=[],
                   postings=[{"id": "p", "account": "Liabilities:Loan", "role": "principal", "currency": "CNY"},
                             {"id": "i", "account": "Expenses:Int", "role": "interest", "currency": "CNY"},
                             {"id": "c", "account": "Assets:Bank", "role": "payment", "currency": "CNY"}])
    occ = Occurrence(schedule_id=1, due_date=datetime.date(2026, 1, 1), loan_seq=1,
                     status="confirmed", frozen_postings=None)
    with pytest.raises(StaleOccurrence, match="confirmed occurrence .* has no frozen_postings"):
        resolve_postings(sch, occ)


def test_confirm_snapshots_frozen_and_readd_reuses_after_event(session, tmp_ledger_config, today):
    """Confirm a loan occurrence: frozen_postings is set to the post-override effective
    split. After adding a prepayment event that would change re-amortization, readd must
    reproduce the FROZEN amounts, not re-amortize."""
    # Extend the tmp ledger with accounts used by the loan schedule
    main = Path(tmp_ledger_config.ledger_main_file)
    main.write_text(
        main.read_text()
        + "2020-01-01 open Assets:Bank\n"
        + "2020-01-01 open Liabilities:Loan\n"
        + "2020-01-01 open Expenses:Interest\n"
    )

    loan_postings = [
        {"id": "p", "account": "Liabilities:Loan", "role": "principal",
         "currency": "CNY", "amount": None, "cost": None, "price": None},
        {"id": "i", "account": "Expenses:Interest", "role": "interest",
         "currency": "CNY", "amount": None, "cost": None, "price": None},
        {"id": "c", "account": "Assets:Bank", "role": "payment",
         "currency": "CNY", "amount": None, "cost": None, "price": None},
    ]
    sch = Schedule(
        name="HomeLoan", narration="Loan installment",
        kind="loan",
        loan={"principal": "120000", "annual_rate": "0.05",
              "term_count": 24, "method": "equal_payment"},
        postings=loan_postings,
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 1),
        events=[],
        tags="",
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)

    # Materialize; anchor_date row (due_date=2026-01-01) corresponds to seq=1
    services.materialize_occurrences(session, tmp_ledger_config, today)
    occs = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
        .order_by(Occurrence.due_date)
    ).all()
    occ = occs[0]
    occ.loan_seq = 1
    occ.loan_event = "regular"
    session.add(occ)
    session.commit()
    session.refresh(occ)

    # Capture what amortization gives for seq=1 before confirming
    pre_amounts = {p.id: p.amount for p in services.resolve_postings(sch, occ)}
    assert all(v is not None for v in pre_amounts.values()), "amortization must fill all role amounts"

    # Confirm
    services.confirm_occurrence(session, tmp_ledger_config, occ.id)
    session.refresh(occ)

    # frozen_postings must be set and equal the pre-confirm amortized split
    assert occ.frozen_postings is not None
    frozen_amounts = {p["id"]: p["amount"] for p in occ.frozen_postings}
    assert frozen_amounts == pre_amounts

    # Add a prepayment event AFTER seq=1; if readd re-amortized, the table would differ
    sch.events = [{"id": "ev1", "kind": "prepayment", "date": "2026-02-01",
                   "amount": "50000", "mode": "shorten_term"}]
    session.add(sch)
    session.commit()
    session.refresh(sch)

    # Simulate the transaction being missing from the ledger
    Path(occ.written_path).write_text("")

    # readd must reproduce the FROZEN amounts, not re-amortize
    services.readd_occurrence(session, tmp_ledger_config, occ.id)
    session.refresh(occ)

    written = Path(occ.written_path).read_text()
    for amount in pre_amounts.values():
        assert amount in written, f"Frozen amount {amount!r} missing from re-added transaction"


def test_materialize_honors_explicit_horizon(session, config):
    from app.models import Schedule, Occurrence
    from sqlmodel import select
    session.add(Schedule(
        name="rent", interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 1), status="active", postings=[],
    ))
    session.commit()
    config.lookahead_days = 0
    today = datetime.date(2026, 1, 1)
    # Default horizon (lookahead 0) yields just the anchor occurrence.
    services.materialize_occurrences(session, config, today)
    base = len(session.exec(select(Occurrence)).all())
    # Explicit 70-day horizon reaches Feb 1 and Mar 1 too.
    services.materialize_occurrences(session, config, today,
                                     horizon=today + datetime.timedelta(days=70))
    after = session.exec(select(Occurrence)).all()
    assert len(after) > base
    assert datetime.date(2026, 3, 1) in {o.due_date for o in after}


def _loan_postings():
    return [
        {"id": "p", "account": "Liabilities:Loan", "role": "principal",
         "currency": "CNY", "amount": None, "cost": None, "price": None},
        {"id": "i", "account": "Expenses:Interest", "role": "interest",
         "currency": "CNY", "amount": None, "cost": None, "price": None},
        {"id": "c", "account": "Assets:Bank", "role": "payment",
         "currency": "CNY", "amount": None, "cost": None, "price": None},
    ]


def _make_loan_schedule(session, events=None):
    sch = Schedule(
        name="HomeLoan", narration="Loan installment", kind="loan",
        loan={"principal": "120000", "annual_rate": "0.05",
              "term_count": 24, "method": "equal_payment"},
        postings=_loan_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 1),
        events=events or [],
        tags="",
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)
    return sch


def test_materialize_loan_prepayment_occurrence(session, config):
    """Prepayment event on a real payment date produces an Occurrence with
    loan_event='prepayment', event_id set, loan_seq=None, and correct sprout_id suffix."""
    event_id = "ev1"
    # anchor=2026-01-01 → payment dates: 2026-01-01 (seq 1), 2026-02-01 (seq 2),
    # 2026-03-01 (seq 3), … ; prepayment lands on 2026-03-01 alongside seq 3.
    sch = _make_loan_schedule(session, events=[
        {"id": event_id, "kind": "prepayment", "date": "2026-03-01",
         "amount": "10000", "mode": "shorten_term"},
    ])
    horizon = datetime.date(2026, 4, 1)
    services.materialize_occurrences(session, config, datetime.date(2026, 1, 1), horizon=horizon)

    occs = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).all()

    pp_occs = [o for o in occs if o.loan_event == "prepayment"]
    assert len(pp_occs) == 1, f"expected 1 prepayment occurrence, got {len(pp_occs)}"
    pp = pp_occs[0]
    assert pp.event_id == event_id
    assert pp.loan_seq is None
    assert pp.sprout_id.endswith(f"-pp{event_id}")

    reg_occs = [o for o in occs if o.loan_event == "regular"]
    assert len(reg_occs) >= 1
    assert all(o.loan_event == "regular" for o in reg_occs)


def test_materialize_loan_is_idempotent(session, config):
    """Running materialize_occurrences twice with the same horizon must not create
    duplicate occurrences (sprout_id uniqueness guards both regular and prepayment rows)."""
    sch = _make_loan_schedule(session, events=[
        {"id": "ev1", "kind": "prepayment", "date": "2026-03-01",
         "amount": "10000", "mode": "shorten_term"},
    ])
    horizon = datetime.date(2026, 4, 1)
    today = datetime.date(2026, 1, 1)
    created_first = services.materialize_occurrences(session, config, today, horizon=horizon)
    created_second = services.materialize_occurrences(session, config, today, horizon=horizon)
    assert created_first > 0
    assert created_second == 0


def test_materialize_creates_loan_occurrences_with_seq(session, config, today):
    from app.services import materialize_occurrences
    from app.models import Schedule, Occurrence
    import datetime
    from sqlmodel import select
    sch = Schedule(name="m", kind="loan", interval_unit="month", interval_count=1,
                   anchor_date=datetime.date(2026, 1, 1),
                   loan={"principal": "120000", "annual_rate": "0.05", "term_count": 24,
                         "method": "equal_principal"}, events=[], postings=[
                       {"id": "p", "account": "Liabilities:L", "role": "principal", "currency": "CNY"},
                       {"id": "i", "account": "Expenses:I", "role": "interest", "currency": "CNY"},
                       {"id": "c", "account": "Assets:B", "role": "payment", "currency": "CNY"}])
    session.add(sch); session.commit()
    materialize_occurrences(session, config, datetime.date(2027, 6, 1),
                            horizon=datetime.date(2027, 12, 31))
    occs = session.exec(select(Occurrence).where(Occurrence.schedule_id == sch.id)).all()
    assert {o.loan_seq for o in occs} >= {1, 2, 3}
    assert all(o.loan_event == "regular" for o in occs)


# ---------------------------------------------------------------------------
# Task 12: skip guard, mark_paid_outside, update_schedule loan pruning
# ---------------------------------------------------------------------------

def test_skip_disabled_on_loan(session, config):
    """skip_occurrence must raise ValueError for loan occurrences; status unchanged."""
    sch = _make_loan_schedule(session)
    # Horizon covers the first 6 monthly installments (Jan-Jun 2026).
    horizon = datetime.date(2026, 6, 8)
    services.materialize_occurrences(session, config, datetime.date(2026, 1, 1), horizon=horizon)

    occs = session.exec(
        sqlmodel.select(Occurrence)
        .where(Occurrence.schedule_id == sch.id, Occurrence.status == "pending")
        .order_by(Occurrence.due_date)
    ).all()
    assert occs, "expected at least one pending loan occurrence"
    occ = occs[0]

    with pytest.raises(ValueError, match="skip is disabled for loan occurrences"):
        services.skip_occurrence(session, occ.id)

    session.refresh(occ)
    assert occ.status == "pending", "occurrence status must remain pending after failed skip"


def test_mark_paid_outside_freezes_without_writing(session, config):
    """mark_paid_outside snapshots the amortized split and marks confirmed; writes no ledger entry."""
    sch = _make_loan_schedule(session)
    horizon = datetime.date(2026, 6, 8)
    today = datetime.date(2026, 1, 1)
    services.materialize_occurrences(session, config, today, horizon=horizon)

    occ = session.exec(
        sqlmodel.select(Occurrence)
        .where(Occurrence.schedule_id == sch.id, Occurrence.status == "pending")
        .order_by(Occurrence.due_date)
    ).first()
    assert occ is not None
    occ_id = occ.id

    # Capture expected amounts from resolve_postings before marking.
    expected = {p.id: p.amount for p in services.resolve_postings(sch, occ)}
    assert all(v is not None for v in expected.values()), "amortization must fill all amounts"

    result = services.mark_paid_outside(session, config, occ_id)

    assert result.status == "confirmed"
    assert result.written_path is None
    assert result.frozen_postings is not None
    frozen = {p["id"]: p["amount"] for p in result.frozen_postings}
    assert frozen == expected, "frozen_postings must match the pre-mark amortized split"

    # No ledger file was created or modified — sprout.bean must not exist.
    from pathlib import Path
    ledger_file = Path(config.ledger_root) / "sprout.bean"
    assert not ledger_file.exists(), "mark_paid_outside must not write any ledger transaction"


def test_update_schedule_prunes_loan_pending_by_amortize(session, config):
    """Shortening term_count via update_schedule deletes pending rows beyond the new payoff.
    Confirmed rows and in-term pending rows are kept."""
    # Build a 6-month loan; materialize all 6 installments (Jan-Jun 2026 within horizon).
    sch = Schedule(
        name="ShortLoan", narration="Loan installment", kind="loan",
        loan={"principal": "60000", "annual_rate": "0.05",
              "term_count": 6, "method": "equal_payment"},
        postings=_loan_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 1),
        events=[],
        tags="",
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)

    today = datetime.date(2026, 6, 8)  # lookahead=0 → horizon=today; covers all 6 installments
    services.materialize_occurrences(session, config, today)

    occs = session.exec(
        sqlmodel.select(Occurrence)
        .where(Occurrence.schedule_id == sch.id)
        .order_by(Occurrence.due_date)
    ).all()
    assert len(occs) == 6, f"expected 6 occurrences, got {len(occs)}"

    # Mark the first occurrence confirmed via mark_paid_outside (no ledger write).
    services.mark_paid_outside(session, config, occs[0].id)
    confirmed_id = occs[0].id
    confirmed_date = occs[0].due_date  # 2026-01-01

    # Shorten to term_count=3; installments 4, 5, 6 are now invalid.
    payload = ScheduleCreate(
        name="ShortLoan", narration="Loan installment",
        kind="loan",
        loan={"principal": "60000", "annual_rate": "0.05",
              "term_count": 3, "method": "equal_payment"},
        postings=_loan_postings(),
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 1),
        events=[],
        tags="",
    )
    services.update_schedule(session, config, sch.id, payload, today)

    remaining = session.exec(
        sqlmodel.select(Occurrence).where(Occurrence.schedule_id == sch.id)
    ).all()

    # Confirmed row must survive even though its date is within the shortened term.
    confirmed_rows = [o for o in remaining if o.id == confirmed_id]
    assert len(confirmed_rows) == 1, "confirmed occurrence must be kept after update"
    assert confirmed_rows[0].status == "confirmed"

    # Pending rows for installments 4, 5, 6 (Apr-Jun 2026) must be deleted.
    # New term ends at month 3 = 2026-03-01; anything due_date > 2026-03-01 and pending must be gone.
    pending_remaining = [o for o in remaining if o.status == "pending"]
    assert all(
        o.due_date <= datetime.date(2026, 3, 1) for o in pending_remaining
    ), f"stale pending rows remain: {[str(o.due_date) for o in pending_remaining if o.due_date > datetime.date(2026, 3, 1)]}"

    # Pending rows for installments 2 and 3 (Feb, Mar 2026) must still exist.
    pending_dates = {o.due_date for o in pending_remaining}
    assert datetime.date(2026, 2, 1) in pending_dates, "installment 2 pending must be kept"
    assert datetime.date(2026, 3, 1) in pending_dates, "installment 3 pending must be kept"
