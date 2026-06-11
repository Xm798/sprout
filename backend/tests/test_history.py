from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session

from app.main import app
from app.db import get_session
from app.config import AppConfig
from app.ledger import load_sprout_ids
from tests.conftest import make_test_engine, new_schedule_payload


@pytest.fixture
def client(tmp_path):
    """API client whose main ledger lives in tmp_path and includes the write
    target (sprout.bean), so reconcile scans can see written transactions."""
    demo = Path(__file__).parent / "fixtures" / "demo.bean"
    main = tmp_path / "main.bean"
    main.write_text(demo.read_text() + '\ninclude "sprout.bean"\n')
    engine = make_test_engine()
    with Session(engine) as s:
        s.add(AppConfig(
            id=1, ledger_main_file=str(main), ledger_root=str(tmp_path),
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


def _seeded_inbox(client) -> list[dict]:
    client.post("/api/schedules", json=new_schedule_payload())
    return client.get("/api/inbox").json()


# ── ledger scan ────────────────────────────────────────────────────────────────

def test_load_sprout_ids_walks_include_tree(tmp_path):
    sub = tmp_path / "sub.bean"
    sub.write_text(
        '2026-01-15 * "Spotify" "sub" #sprout\n'
        '  sprout-id: "sch1-20260115"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
        "\n"
        '2026-02-01 * "Manual" "no sprout id"\n'
        "  Expenses:Subscription  1.00 USD\n"
        "  Assets:CreditCard\n"
    )
    main = tmp_path / "main.bean"
    main.write_text(
        "2020-01-01 open Assets:CreditCard\n"
        "2020-01-01 open Expenses:Subscription\n"
        'include "sub.bean"\n'
    )
    assert load_sprout_ids(str(main)) == {"sch1-20260115"}


def test_load_sprout_ids_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_sprout_ids(str(tmp_path / "nope.bean"))
    with pytest.raises(FileNotFoundError):
        load_sprout_ids("")


# ── GET /history ───────────────────────────────────────────────────────────────

def test_history_lists_confirmed_and_skipped_not_pending(client):
    items = _seeded_inbox(client)
    assert len(items) >= 2
    first, second = items[0], items[1]  # inbox is due_date ascending
    assert client.post(f"/api/inbox/{first['id']}/confirm", json={}).status_code == 200
    assert client.post(f"/api/inbox/{second['id']}/skip").status_code == 200

    history = client.get("/api/history").json()
    assert {o["status"] for o in history} == {"confirmed", "skipped"}
    assert {o["id"] for o in history} == {first["id"], second["id"]}
    # Newest due date first: the skipped occurrence is one month later.
    assert history[0]["id"] == second["id"]


# ── GET /history/check ─────────────────────────────────────────────────────────

def test_check_reports_missing_after_manual_delete(client, tmp_path):
    occ_id = _seeded_inbox(client)[0]["id"]
    client.post(f"/api/inbox/{occ_id}/confirm", json={})

    r = client.get("/api/history/check")
    assert r.status_code == 200, r.text
    assert r.json()["missing"] == []

    # Simulate the user wiping the written transaction in their editor.
    (tmp_path / "sprout.bean").write_text("")
    assert client.get("/api/history/check").json()["missing"] == [occ_id]


def test_check_unconfigured_ledger_422(client, tmp_path):
    cfg = client.get("/api/config").json()
    cfg["ledger_main_file"] = str(tmp_path / "gone.bean")
    client.put("/api/config", json=cfg)
    assert client.get("/api/history/check").status_code == 422


# ── POST /history/{id}/readd ───────────────────────────────────────────────────

def test_readd_restores_missing_transaction(client, tmp_path):
    occ = _seeded_inbox(client)[0]
    confirmed = client.post(f"/api/inbox/{occ['id']}/confirm", json={}).json()
    sprout_id = confirmed["sprout_id"]
    ledger = tmp_path / "sprout.bean"
    assert sprout_id in ledger.read_text()

    # A bare mention of the id (e.g. in a comment) must not trip the presence
    # guard — only the exact `sprout-id: "..."` metadata line counts.
    ledger.write_text(f"; manually removed {sprout_id}\n")
    r = client.post(f"/api/history/{occ['id']}/readd")
    assert r.status_code == 200, r.text
    assert r.json()["written_path"] == str(ledger)
    assert sprout_id in ledger.read_text()
    assert client.get("/api/history/check").json()["missing"] == []


def test_readd_honors_schedule_target_file(client, tmp_path):
    """Re-add must restore into the schedule's target_file, not the global
    write-strategy file."""
    client.post("/api/schedules", json=new_schedule_payload(target_file="rent.bean"))
    occ = client.get("/api/inbox").json()[0]
    confirmed = client.post(f"/api/inbox/{occ['id']}/confirm", json={}).json()
    rent = tmp_path / "rent.bean"
    assert confirmed["written_path"] == str(rent)

    rent.write_text("")
    assert client.get("/api/history/check").json()["missing"] == [occ["id"]]
    r = client.post(f"/api/history/{occ['id']}/readd")
    assert r.status_code == 200, r.text
    assert r.json()["written_path"] == str(rent)
    assert confirmed["sprout_id"] in rent.read_text()
    assert not (tmp_path / "sprout.bean").exists()
    assert client.get("/api/history/check").json()["missing"] == []


def test_readd_still_present_409(client):
    occ_id = _seeded_inbox(client)[0]["id"]
    client.post(f"/api/inbox/{occ_id}/confirm", json={})
    r = client.post(f"/api/history/{occ_id}/readd")
    assert r.status_code == 409
    assert "still present" in r.json()["detail"]


def test_readd_pending_409(client):
    occ_id = _seeded_inbox(client)[0]["id"]
    assert client.post(f"/api/history/{occ_id}/readd").status_code == 409


def test_readd_missing_occurrence_404(client):
    assert client.post("/api/history/99999/readd").status_code == 404


def test_readd_unreachable_target_409(client, tmp_path):
    """If the include line is gone, the scan flags the occurrence missing, but
    re-add must NOT double-append into the unreachable target file."""
    occ_id = _seeded_inbox(client)[0]["id"]
    client.post(f"/api/inbox/{occ_id}/confirm", json={})

    demo = Path(__file__).parent / "fixtures" / "demo.bean"
    (tmp_path / "main.bean").write_text(demo.read_text())  # drop the include

    assert client.get("/api/history/check").json()["missing"] == [occ_id]
    r = client.post(f"/api/history/{occ_id}/readd")
    assert r.status_code == 409
    assert "include" in r.json()["detail"]
    # Exactly one copy of the transaction remains in the target file.
    assert (tmp_path / "sprout.bean").read_text().count("sprout-id") == 1


# ── GET /history/{id}/written ──────────────────────────────────────────────────

def _confirm_first(client, json_body=None) -> dict:
    occ = _seeded_inbox(client)[0]
    r = client.post(f"/api/inbox/{occ['id']}/confirm", json=json_body or {})
    assert r.status_code == 200, r.text
    return r.json()


def test_get_written_returns_block_and_path(client, tmp_path):
    occ = _confirm_first(client)
    r = client.get(f"/api/history/{occ['id']}/written")
    assert r.status_code == 200, r.text
    body = r.json()
    assert Path(body["path"]).resolve() == (tmp_path / "sprout.bean").resolve()
    assert body["text"].startswith("2026-01-15")
    assert f'sprout-id: "{occ["sprout_id"]}"' in body["text"]


def test_get_written_returns_manual_edits_verbatim(client, tmp_path):
    occ = _confirm_first(client)
    edited = (
        '2026-01-15 * "Spotify" "sub EDITED by hand" #sprout\n'
        f'  sprout-id: "{occ["sprout_id"]}"\n'
        "  ; user note kept inside the block\n"
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    (tmp_path / "sprout.bean").write_text(edited)
    r = client.get(f"/api/history/{occ['id']}/written")
    assert r.status_code == 200, r.text
    assert r.json()["text"] == edited


def test_get_written_not_confirmed_409(client):
    occ_id = _seeded_inbox(client)[0]["id"]
    assert client.get(f"/api/history/{occ_id}/written").status_code == 409


def test_get_written_missing_transaction_409(client, tmp_path):
    occ = _confirm_first(client)
    (tmp_path / "sprout.bean").write_text("")
    r = client.get(f"/api/history/{occ['id']}/written")
    assert r.status_code == 409
    assert "not present" in r.json()["detail"]


def test_get_written_unknown_occurrence_404(client):
    assert client.get("/api/history/99999/written").status_code == 404


# ── POST /history/{id}/unconfirm ───────────────────────────────────────────────

def test_unconfirm_removes_block_and_returns_to_inbox(client, tmp_path):
    items = _seeded_inbox(client)
    first, second = items[0], items[1]
    confirmed = client.post(
        f"/api/inbox/{first['id']}/confirm",
        json={"override_amounts": {"main": "20.00"}},
    ).json()
    client.post(f"/api/inbox/{second['id']}/confirm", json={})

    r = client.post(f"/api/history/{first['id']}/unconfirm")
    assert r.status_code == 200, r.text
    occ = r.json()
    assert occ["status"] == "pending"
    assert occ["written_path"] is None
    assert occ["confirmed_at"] is None
    assert occ["override_amounts"] == {"main": "20.00"}
    assert occ["sprout_id"] == confirmed["sprout_id"]

    # Exactly the target block is gone; the second transaction survives.
    ledger = (tmp_path / "sprout.bean").read_text()
    assert confirmed["sprout_id"] not in ledger
    assert "sch1-20260215" in ledger

    assert first["id"] in {o["id"] for o in client.get("/api/inbox").json()}
    assert client.get("/api/history/check").json()["missing"] == []


def test_unconfirm_deletes_from_loader_file_not_written_path(client, tmp_path):
    occ = _confirm_first(client)
    sprout = tmp_path / "sprout.bean"
    other = tmp_path / "other.bean"
    main = tmp_path / "main.bean"
    # The user moved the transaction into another included file; written_path
    # still points at sprout.bean and must be treated as an audit hint only.
    other.write_text(sprout.read_text())
    sprout.write_text("")
    main.write_text(main.read_text() + 'include "other.bean"\n')

    r = client.post(f"/api/history/{occ['id']}/unconfirm")
    assert r.status_code == 200, r.text
    assert occ["sprout_id"] not in other.read_text()
    assert sprout.read_text() == ""  # untouched


def test_unconfirm_only_transaction_leaves_empty_included_file(client, tmp_path):
    client.post("/api/schedules", json=new_schedule_payload(target_file="rent.bean"))
    occ = client.get("/api/inbox").json()[0]
    client.post(f"/api/inbox/{occ['id']}/confirm", json={})
    rent = tmp_path / "rent.bean"
    assert occ["sprout_id"] is not None

    r = client.post(f"/api/history/{occ['id']}/unconfirm")
    assert r.status_code == 200, r.text
    assert rent.exists() and rent.read_text() == ""
    assert 'include "rent.bean"' in (tmp_path / "main.bean").read_text()
    assert client.get("/api/history/check").status_code == 200


def test_unconfirm_round_trip_writes_same_id_once(client, tmp_path):
    occ = _confirm_first(client)
    assert client.post(f"/api/history/{occ['id']}/unconfirm").status_code == 200

    r = client.post(
        f"/api/inbox/{occ['id']}/confirm",
        json={"override_amounts": {"main": "20.00"}},
    )
    assert r.status_code == 200, r.text
    ledger = (tmp_path / "sprout.bean").read_text()
    assert ledger.count(f'sprout-id: "{occ["sprout_id"]}"') == 1
    assert "20.00" in ledger
    assert client.get("/api/history/check").json()["missing"] == []


def test_unconfirm_prunes_stale_override_keys(client):
    sch = client.post("/api/schedules", json=new_schedule_payload()).json()
    occ = client.get("/api/inbox").json()[0]
    client.post(
        f"/api/inbox/{occ['id']}/confirm",
        json={"override_amounts": {"main": "20.00"}},
    )
    # Restructure the postings: the "main" id no longer exists. update_schedule
    # only prunes pending rows, so the confirmed occurrence keeps the key.
    restructured = new_schedule_payload(postings=[
        {"id": "primary", "account": "Expenses:Subscription", "amount": "15.00",
         "currency": "USD", "cost": None, "price": None},
        {"id": "settle", "account": "Assets:CreditCard", "amount": None,
         "currency": None, "cost": None, "price": None},
    ])
    assert client.put(f"/api/schedules/{sch['id']}", json=restructured).status_code == 200

    r = client.post(f"/api/history/{occ['id']}/unconfirm")
    assert r.status_code == 200, r.text
    assert r.json()["override_amounts"] == {}
    # Back in the inbox, the occurrence previews cleanly.
    assert client.get(f"/api/inbox/{occ['id']}/preview").status_code == 200


def test_unconfirm_missing_transaction_reverts_status_without_file_writes(client, tmp_path):
    occ = _confirm_first(client)
    sprout = tmp_path / "sprout.bean"
    main = tmp_path / "main.bean"
    sprout.write_text("")
    sprout_before, main_before = sprout.read_bytes(), main.read_bytes()

    r = client.post(f"/api/history/{occ['id']}/unconfirm")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    assert sprout.read_bytes() == sprout_before
    assert main.read_bytes() == main_before


def test_unconfirm_duplicate_sprout_id_409_file_untouched(client, tmp_path):
    occ = _confirm_first(client)
    sprout = tmp_path / "sprout.bean"
    dup = (
        '\n2026-02-15 * "Spotify" "duplicated by hand" #sprout\n'
        f'  sprout-id: "{occ["sprout_id"]}"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    sprout.write_text(sprout.read_text() + dup)
    before = sprout.read_bytes()

    r = client.post(f"/api/history/{occ['id']}/unconfirm")
    assert r.status_code == 409
    assert "manually" in r.json()["detail"]
    assert sprout.read_bytes() == before
    assert client.get(f"/api/history/{occ['id']}/written").status_code == 409


def test_unconfirm_restores_file_when_balance_breaks(client, tmp_path):
    occ = _confirm_first(client)
    main = tmp_path / "main.bean"
    # Passes now (the confirmed transaction puts -15.00 on the card), but
    # would fail once that transaction is removed.
    main.write_text(main.read_text() + "\n2026-02-01 balance Assets:CreditCard  -15.00 USD\n")
    sprout = tmp_path / "sprout.bean"
    before = sprout.read_bytes()

    r = client.post(f"/api/history/{occ['id']}/unconfirm")
    assert r.status_code == 422
    assert "break the ledger" in r.json()["detail"]
    assert sprout.read_bytes() == before  # byte-identical restore
    history = client.get("/api/history").json()
    assert [o["status"] for o in history if o["id"] == occ["id"]] == ["confirmed"]


def test_unconfirm_restores_file_on_multiline_narration(client, tmp_path):
    occ = _confirm_first(client)
    sprout = tmp_path / "sprout.bean"
    # Legal beancount: the narration string spans two lines, so the block's
    # continuation sits at column 0 and the line surgery would truncate it.
    sprout.write_text(
        '2026-01-15 * "Spotify" "line one\nline two" #sprout\n'
        f'  sprout-id: "{occ["sprout_id"]}"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    before = sprout.read_bytes()

    r = client.post(f"/api/history/{occ['id']}/unconfirm")
    assert r.status_code == 422
    assert sprout.read_bytes() == before


def test_unconfirm_pending_409(client):
    occ_id = _seeded_inbox(client)[0]["id"]
    assert client.post(f"/api/history/{occ_id}/unconfirm").status_code == 409


def test_unconfirm_unknown_occurrence_404(client):
    assert client.post("/api/history/99999/unconfirm").status_code == 404


def test_unconfirm_unconfigured_ledger_422(client, tmp_path):
    occ = _confirm_first(client)
    cfg = client.get("/api/config").json()
    cfg["ledger_main_file"] = str(tmp_path / "gone.bean")
    client.put("/api/config", json=cfg)
    assert client.post(f"/api/history/{occ['id']}/unconfirm").status_code == 422


# ── confirm-path duplicate guard ───────────────────────────────────────────────

def test_confirm_refuses_when_target_file_already_has_id(client, tmp_path):
    occ = _seeded_inbox(client)[0]
    pre_existing = (
        '2026-01-15 * "Manual" "copy already in the target file" #sprout\n'
        f'  sprout-id: "{occ["sprout_id"]}"\n'
        "  Expenses:Subscription  15.00 USD\n"
        "  Assets:CreditCard\n"
    )
    sprout = tmp_path / "sprout.bean"
    sprout.write_text(pre_existing)
    before = sprout.read_bytes()

    r = client.post(f"/api/inbox/{occ['id']}/confirm", json={})
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]
    assert sprout.read_bytes() == before  # nothing appended
    assert occ["id"] in {o["id"] for o in client.get("/api/inbox").json()}


# ── POST /history/{id}/unskip ──────────────────────────────────────────────────

def test_unskip_returns_skipped_to_inbox(client):
    occ_id = _seeded_inbox(client)[0]["id"]
    client.post(f"/api/inbox/{occ_id}/skip")

    r = client.post(f"/api/history/{occ_id}/unskip")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    assert occ_id in {o["id"] for o in client.get("/api/inbox").json()}
    assert occ_id not in {o["id"] for o in client.get("/api/history").json()}


def test_unskip_non_skipped_409(client):
    items = _seeded_inbox(client)
    pending_id, confirm_id = items[0]["id"], items[1]["id"]
    client.post(f"/api/inbox/{confirm_id}/confirm", json={})
    assert client.post(f"/api/history/{pending_id}/unskip").status_code == 409
    assert client.post(f"/api/history/{confirm_id}/unskip").status_code == 409


def test_unskip_unknown_occurrence_404(client):
    assert client.post("/api/history/99999/unskip").status_code == 404
