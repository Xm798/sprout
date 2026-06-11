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
