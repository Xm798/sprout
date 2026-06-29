import datetime
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session

from app.main import app
from app.db import get_session
from app.config import AppConfig
from app.models import Occurrence
from tests.conftest import make_test_engine, new_schedule_payload


@pytest.fixture
def client(tmp_path):
    demo = Path(__file__).parent / "fixtures" / "demo.bean"
    engine = make_test_engine()
    with Session(engine) as s:
        s.add(AppConfig(
            id=1, ledger_main_file=str(demo), ledger_root=str(tmp_path),
            write_mode="single_file", single_file_name="sprout.bean",
            default_tag="sprout", lookahead_days=0,
        ))
        s.commit()

    def _override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
    if engine.dialect.name != "sqlite":
        SQLModel.metadata.drop_all(engine)
    engine.dispose()


@contextmanager
def _db_session():
    """Session from the active get_session override, properly closed.
    A bare `next(override())` leaks an open transaction whose table locks
    deadlock the next test's drop_all on Postgres."""
    gen = app.dependency_overrides[get_session]()
    try:
        yield next(gen)
    finally:
        gen.close()


def test_create_and_list_schedules(client):
    r = client.post("/api/schedules", json=new_schedule_payload())
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.get("/api/schedules").json()[0]["id"] == sid


def test_inbox_lists_pending(client):
    client.post("/api/schedules", json=new_schedule_payload())
    r = client.get("/api/inbox")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["status"] == "pending"


def test_preview_then_confirm(client):
    client.post("/api/schedules", json=new_schedule_payload())
    occ_id = client.get("/api/inbox").json()[0]["id"]
    prev = client.get(f"/api/inbox/{occ_id}/preview")
    assert "Expenses:Subscription" in prev.json()["text"]
    r = client.post(f"/api/inbox/{occ_id}/confirm", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


def test_skip(client):
    client.post("/api/schedules", json=new_schedule_payload())
    occ_id = client.get("/api/inbox").json()[0]["id"]
    r = client.post(f"/api/inbox/{occ_id}/skip")
    assert r.json()["status"] == "skipped"


def test_accounts_and_currencies(client):
    assert "Assets:CreditCard" in client.get("/api/accounts").json()
    assert client.get("/api/currencies").json() == ["USD", "CNY"]


def test_get_and_update_config(client):
    cfg = client.get("/api/config").json()
    assert cfg["write_mode"] == "single_file"
    assert cfg["default_currency"] == "USD"
    r = client.put("/api/config", json={**cfg, "lookahead_days": 7, "default_currency": "CNY"})
    assert r.json()["lookahead_days"] == 7
    assert r.json()["default_currency"] == "CNY"


def test_preview_missing_occurrence_404(client):
    assert client.get("/api/inbox/99999/preview").status_code == 404


def test_confirm_missing_occurrence_404(client):
    assert client.post("/api/inbox/99999/confirm", json={}).status_code == 404


def test_skip_missing_occurrence_404(client):
    assert client.post("/api/inbox/99999/skip").status_code == 404


def test_create_schedule_returns_headline(client):
    r = client.post("/api/schedules", json=new_schedule_payload())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["headline_amount"] == "15.00"
    assert data["headline_currency"] == "USD"
    assert data["postings"][0]["account"] == "Expenses:Subscription"


def test_create_rejects_two_blank_legs(client):
    bad = new_schedule_payload(postings=[
        {"id": "a", "account": "Assets:One", "amount": None, "currency": None,
         "cost": None, "price": None},
        {"id": "b", "account": "Assets:Two", "amount": None, "currency": None,
         "cost": None, "price": None},
    ])
    assert client.post("/api/schedules", json=bad).status_code == 422


def test_post_preview_reflects_transient_override(client):
    client.post("/api/schedules", json=new_schedule_payload())
    occ = client.get("/api/inbox").json()[0]
    r = client.post(
        f"/api/inbox/{occ['id']}/preview",
        json={"override_amounts": {"main": "7.50"}},
    )
    assert r.status_code == 200
    assert "7.50 USD" in r.json()["text"]


def test_update_schedule_returns_updated_headline(client):
    sid = client.post("/api/schedules", json=new_schedule_payload()).json()["id"]
    updated = new_schedule_payload()
    updated["postings"][0]["amount"] = "42.00"
    r = client.put(f"/api/schedules/{sid}", json=updated)
    assert r.status_code == 200, r.text
    assert r.json()["headline_amount"] == "42.00"


def test_update_missing_schedule_404(client):
    assert client.put("/api/schedules/99999", json=new_schedule_payload()).status_code == 404


def _inbox_occ_id(client) -> int:
    client.post("/api/schedules", json=new_schedule_payload())
    return client.get("/api/inbox").json()[0]["id"]


def test_confirm_malformed_amount_422(client):
    occ_id = _inbox_occ_id(client)
    r = client.post(f"/api/inbox/{occ_id}/confirm", json={"override_amounts": {"main": "abc"}})
    assert r.status_code == 422
    assert "is not a number" in r.json()["detail"]


def test_post_preview_malformed_amount_422(client):
    occ_id = _inbox_occ_id(client)
    r = client.post(f"/api/inbox/{occ_id}/preview", json={"override_amounts": {"main": "abc"}})
    assert r.status_code == 422
    assert "is not a number" in r.json()["detail"]


def test_confirm_unknown_override_key_422(client):
    """Unknown posting id in override_amounts must 422, keep occ pending, not persist bogus key."""
    client.post("/api/schedules", json=new_schedule_payload())
    occ = client.get("/api/inbox").json()[0]
    occ_id = occ["id"]
    r = client.post(f"/api/inbox/{occ_id}/confirm", json={"override_amounts": {"bogus": "99.00"}})
    assert r.status_code == 422
    assert "bogus" in r.json()["detail"]

    # Occurrence must still be pending
    inbox = client.get("/api/inbox").json()
    assert any(o["id"] == occ_id and o["status"] == "pending" for o in inbox)

    # override_amounts must not contain the bogus key
    override_amounts = next(o["override_amounts"] for o in inbox if o["id"] == occ_id)
    assert override_amounts is None or "bogus" not in (override_amounts or {})


def test_post_preview_unknown_override_key_422(client):
    """Unknown posting id in preview override_amounts must 422."""
    occ_id = _inbox_occ_id(client)
    r = client.post(f"/api/inbox/{occ_id}/preview", json={"override_amounts": {"bogus": "99.00"}})
    assert r.status_code == 422
    assert "bogus" in r.json()["detail"]


def _set_stored_override(occ_id: int, overrides: dict) -> None:
    """Write occ.override_amounts directly via the session, bypassing the API
    (which now rejects unknown keys) to simulate legacy/stale persisted data."""
    from app.models import Occurrence
    with _db_session() as session:
        occ = session.get(Occurrence, occ_id)
        occ.override_amounts = overrides
        session.add(occ)
        session.commit()


def test_get_preview_stale_stored_override_key_422(client):
    """A stale key in the STORED occ.override_amounts (persisted before validation
    existed, or orphaned by a schedule edit) must 422 on GET preview, not no-op."""
    occ_id = _inbox_occ_id(client)
    _set_stored_override(occ_id, {"stale": "99.00"})
    r = client.get(f"/api/inbox/{occ_id}/preview")
    assert r.status_code == 422
    assert "stale" in r.json()["detail"]


def test_post_preview_stale_stored_override_key_422(client):
    """POST preview must also reject stale STORED override keys, even when the
    transient body is clean."""
    occ_id = _inbox_occ_id(client)
    _set_stored_override(occ_id, {"stale": "99.00"})
    r = client.post(f"/api/inbox/{occ_id}/preview", json={"override_amounts": {"main": "7.50"}})
    assert r.status_code == 422
    assert "stale" in r.json()["detail"]


# ── cascade delete ─────────────────────────────────────────────────────────────

def test_delete_schedule_removes_occurrences(client):
    """Deleting a schedule must remove all its occurrences from GET /inbox
    and from the DB (all statuses, not just pending)."""
    from sqlmodel import select
    from app.models import Occurrence
    client.post("/api/schedules", json=new_schedule_payload())
    inbox_before = client.get("/api/inbox").json()
    assert len(inbox_before) >= 1
    sid = inbox_before[0]["schedule_id"]
    # Move one occurrence out of "pending" so the DB check covers non-pending rows
    client.post(f"/api/inbox/{inbox_before[0]['id']}/skip")
    r = client.delete(f"/api/schedules/{sid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Occurrences for this schedule must not appear in inbox
    inbox_after = client.get("/api/inbox").json()
    assert all(o["schedule_id"] != sid for o in inbox_after)
    # DB-level: no occurrence rows of ANY status survive
    with _db_session() as session:
        remaining = session.exec(
            select(Occurrence).where(Occurrence.schedule_id == sid)
        ).all()
    assert remaining == []


def test_delete_missing_schedule_404(client):
    assert client.delete("/api/schedules/99999").status_code == 404


# ── orphan occurrence → 404 ────────────────────────────────────────────────────

def _forge_orphan_occurrence(occ_id: int) -> None:
    """Delete the schedule row while leaving the occurrence row intact,
    simulating pre-fix data (or a non-cascade delete)."""
    from sqlalchemy import text
    from app.models import Schedule
    with _db_session() as session:
        occ = session.get(Occurrence, occ_id)
        sch = session.get(Schedule, occ.schedule_id)
        if session.get_bind().dialect.name == "postgresql":
            # Postgres enforces the schedule FK that SQLite leaves off; disable
            # FK triggers for this transaction to forge the legacy orphan state.
            session.execute(text("SET LOCAL session_replication_role = 'replica'"))
        session.delete(sch)
        session.commit()


def test_get_preview_orphan_occurrence_404(client):
    """GET /inbox/{id}/preview on an orphan occurrence returns 404, not 500."""
    occ_id = _inbox_occ_id(client)
    _forge_orphan_occurrence(occ_id)
    r = client.get(f"/api/inbox/{occ_id}/preview")
    assert r.status_code == 404


def test_post_preview_orphan_occurrence_404(client):
    """POST /inbox/{id}/preview on an orphan occurrence returns 404, not 500."""
    occ_id = _inbox_occ_id(client)
    _forge_orphan_occurrence(occ_id)
    r = client.post(f"/api/inbox/{occ_id}/preview", json={})
    assert r.status_code == 404


def test_confirm_orphan_occurrence_404(client):
    """POST /inbox/{id}/confirm on an orphan occurrence returns 404, not 500."""
    occ_id = _inbox_occ_id(client)
    _forge_orphan_occurrence(occ_id)
    r = client.post(f"/api/inbox/{occ_id}/confirm", json={})
    assert r.status_code == 404


# ── schedule edited between preview and confirm ─────────────────────────────────

def test_confirm_rejects_override_for_leg_renamed_after_preview(client, tmp_path):
    """If the schedule's amount-leg posting id changes between preview and confirm,
    confirming with the now-stale id must 422 (occurrence stays pending, ledger
    untouched), while confirming with the new id succeeds and writes the override."""
    sid = client.post("/api/schedules", json=new_schedule_payload()).json()["id"]
    occ_id = client.get("/api/inbox").json()[0]["id"]
    ledger = tmp_path / "sprout.bean"

    # Preview an override keyed on the original amount-leg id ("main").
    prev = client.post(
        f"/api/inbox/{occ_id}/preview", json={"override_amounts": {"main": "12.34"}}
    )
    assert prev.status_code == 200, prev.text
    assert "12.34" in prev.json()["text"]

    # Rename the amount leg's posting id, mirroring a user editing the schedule.
    edited = new_schedule_payload()
    edited["postings"][0]["id"] = "main2"
    assert client.put(f"/api/schedules/{sid}", json=edited).status_code == 200

    # Confirming with the stale id must be rejected, leave the occurrence pending,
    # and write nothing to the ledger.
    stale = client.post(
        f"/api/inbox/{occ_id}/confirm", json={"override_amounts": {"main": "12.34"}}
    )
    assert stale.status_code == 422
    assert "main" in stale.json()["detail"]
    inbox = client.get("/api/inbox").json()
    assert any(o["id"] == occ_id and o["status"] == "pending" for o in inbox)
    assert not ledger.exists()

    # Confirming with the new id succeeds and persists the 12.34 override.
    ok = client.post(
        f"/api/inbox/{occ_id}/confirm", json={"override_amounts": {"main2": "12.34"}}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "confirmed"
    assert "12.34" in ledger.read_text()


# ── target_file / bean-files ───────────────────────────────────────────────────

def test_create_schedule_with_target_file(client):
    r = client.post("/api/schedules", json=new_schedule_payload(target_file="subs/spotify.bean"))
    assert r.status_code == 200, r.text
    assert r.json()["target_file"] == "subs/spotify.bean"
    # round-trips through list and update
    sid = r.json()["id"]
    assert client.get(f"/api/schedules/{sid}").json()["target_file"] == "subs/spotify.bean"
    r2 = client.put(f"/api/schedules/{sid}", json=new_schedule_payload(target_file="other.bean"))
    assert r2.status_code == 200, r2.text
    assert r2.json()["target_file"] == "other.bean"


def test_create_schedule_blank_target_file_normalizes_to_null(client):
    r = client.post("/api/schedules", json=new_schedule_payload(target_file="  "))
    assert r.status_code == 200, r.text
    assert r.json()["target_file"] is None


@pytest.mark.parametrize("bad", ["/abs/x.bean", "../up.bean", "x.txt", "a\\b.bean"])
def test_create_schedule_rejects_bad_target_file(client, bad):
    r = client.post("/api/schedules", json=new_schedule_payload(target_file=bad))
    assert r.status_code == 422


def test_bean_files_lists_nested_relative_paths(client, tmp_path):
    (tmp_path / "rent.bean").write_text("")
    (tmp_path / "loans").mkdir()
    (tmp_path / "loans" / "car.bean").write_text("")
    (tmp_path / "notes.txt").write_text("")
    r = client.get("/api/bean-files")
    assert r.status_code == 200
    files = r.json()
    assert "rent.bean" in files
    assert "loans/car.bean" in files
    assert "notes.txt" not in files
    assert files == sorted(files)


# ── POST /api/schedules/parse ────────────────────────────────────────────────

def test_parse_returns_transaction_fields(client):
    r = client.post("/api/schedules/parse", json={"text":
        '2026-06-15 * "Spotify" "sub"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "name" not in body  # name stays user-entered, never parsed from bean
    assert body["payee"] == "Spotify"
    assert body["narration"] == "sub"
    assert body["anchor_date"] == "2026-06-15"
    assert body["tags"] == ""
    assert body["warnings"] == []
    assert [p["account"] for p in body["postings"]] == \
        ["Expenses:Subscription", "Assets:CreditCard"]
    assert body["postings"][1]["amount"] is None
    assert all(p["id"] for p in body["postings"])


def test_parse_route_not_shadowed_by_schedule_id(client):
    # "parse" must match the literal route, not /{schedule_id} (which 422s on int).
    r = client.post("/api/schedules/parse", json={"text":
        '2026-06-15 * "x" ""\n  Assets:B  1 USD\n  Equity:D\n'})
    assert r.status_code == 200, r.text


def test_parse_surfaces_structural_warning(client):
    r = client.post("/api/schedules/parse", json={"text":
        '2026-06-15 * "x" ""\n  Assets:B  1 USD\n'})
    assert r.status_code == 200, r.text
    assert r.json()["warnings"]


@pytest.mark.parametrize("text", [
    "",
    "2026-06-01 open Assets:Bank\n",
    '2026-06-01 * "a" ""\n  Assets:B 1 USD\n  Equity:D\n'
    '2026-06-02 * "b" ""\n  Assets:B 2 USD\n  Equity:D\n',
    "garbage @@@ 2026-13-99",
])
def test_parse_rejects_bad_input(client, text):
    r = client.post("/api/schedules/parse", json={"text": text})
    assert r.status_code == 400, r.text
    assert r.json()["detail"]


def test_exchange_rate_endpoint_returns_rate(client, monkeypatch):
    import datetime
    from decimal import Decimal
    from app import exchange_rates as ex

    def fake_fetch(source, base, quote, on):
        assert source == "frankfurter"
        return Decimal("0.8673"), datetime.date(2026, 6, 25)

    monkeypatch.setattr(ex, "_network_fetch", fake_fetch)
    r = client.get("/api/exchange-rates/rate",
                   params={"base": "HKD", "quote": "CNY"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rate"] == "0.8673"
    assert body["source"] == "frankfurter"
    assert body["base"] == "HKD" and body["quote"] == "CNY"


def test_exchange_rate_endpoint_maps_upstream_failure_to_502(client, monkeypatch):
    from app import exchange_rates as ex

    def boom(source, base, quote, on):
        raise ex.RateError("upstream down")

    monkeypatch.setattr(ex, "_network_fetch", boom)
    r = client.get("/api/exchange-rates/rate",
                   params={"base": "HKD", "quote": "CNY"})
    assert r.status_code == 502, r.text
