import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session

from app.main import app
from app.db import get_session
from app.config import AppConfig
from tests.conftest import make_test_engine


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


def _new_schedule_payload(**over):
    body = {
        "name": "Spotify", "narration": "sub",
        "postings": [
            {"id": "main", "account": "Expenses:Subscription", "amount": "15.00",
             "currency": "USD", "cost": None, "price": None},
            {"id": "bal", "account": "Assets:CreditCard", "amount": None,
             "currency": None, "cost": None, "price": None},
        ],
        "interval_unit": "month", "interval_count": 1,
        "anchor_date": "2026-01-15", "max_count": 6, "tags": "sprout",
        "status": "active",
    }
    body.update(over)
    return body


def test_create_and_list_schedules(client):
    r = client.post("/api/schedules", json=_new_schedule_payload())
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.get("/api/schedules").json()[0]["id"] == sid


def test_inbox_lists_pending(client):
    client.post("/api/schedules", json=_new_schedule_payload())
    r = client.get("/api/inbox")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["status"] == "pending"


def test_preview_then_confirm(client):
    client.post("/api/schedules", json=_new_schedule_payload())
    occ_id = client.get("/api/inbox").json()[0]["id"]
    prev = client.get(f"/api/inbox/{occ_id}/preview")
    assert "Expenses:Subscription" in prev.json()["text"]
    r = client.post(f"/api/inbox/{occ_id}/confirm", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


def test_skip(client):
    client.post("/api/schedules", json=_new_schedule_payload())
    occ_id = client.get("/api/inbox").json()[0]["id"]
    r = client.post(f"/api/inbox/{occ_id}/skip")
    assert r.json()["status"] == "skipped"


def test_accounts_and_currencies(client):
    assert "Assets:CreditCard" in client.get("/api/accounts").json()
    assert client.get("/api/currencies").json() == ["USD", "CNY"]


def test_get_and_update_config(client):
    cfg = client.get("/api/config").json()
    assert cfg["write_mode"] == "single_file"
    r = client.put("/api/config", json={**cfg, "lookahead_days": 7})
    assert r.json()["lookahead_days"] == 7


def test_preview_missing_occurrence_404(client):
    assert client.get("/api/inbox/99999/preview").status_code == 404


def test_confirm_missing_occurrence_404(client):
    assert client.post("/api/inbox/99999/confirm", json={}).status_code == 404


def test_skip_missing_occurrence_404(client):
    assert client.post("/api/inbox/99999/skip").status_code == 404


def test_create_schedule_returns_headline(client):
    r = client.post("/api/schedules", json=_new_schedule_payload())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["headline_amount"] == "15.00"
    assert data["headline_currency"] == "USD"
    assert data["postings"][0]["account"] == "Expenses:Subscription"


def test_create_rejects_two_blank_legs(client):
    bad = _new_schedule_payload(postings=[
        {"id": "a", "account": "Assets:One", "amount": None, "currency": None,
         "cost": None, "price": None},
        {"id": "b", "account": "Assets:Two", "amount": None, "currency": None,
         "cost": None, "price": None},
    ])
    assert client.post("/api/schedules", json=bad).status_code == 422


def test_post_preview_reflects_transient_override(client):
    client.post("/api/schedules", json=_new_schedule_payload())
    occ = client.get("/api/inbox").json()[0]
    r = client.post(
        f"/api/inbox/{occ['id']}/preview",
        json={"override_amounts": {"main": "7.50"}},
    )
    assert r.status_code == 200
    assert "7.50 USD" in r.json()["text"]


def test_update_schedule_returns_updated_headline(client):
    sid = client.post("/api/schedules", json=_new_schedule_payload()).json()["id"]
    updated = _new_schedule_payload()
    updated["postings"][0]["amount"] = "42.00"
    r = client.put(f"/api/schedules/{sid}", json=updated)
    assert r.status_code == 200, r.text
    assert r.json()["headline_amount"] == "42.00"


def test_update_missing_schedule_404(client):
    assert client.put("/api/schedules/99999", json=_new_schedule_payload()).status_code == 404


def _inbox_occ_id(client) -> int:
    client.post("/api/schedules", json=_new_schedule_payload())
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
    client.post("/api/schedules", json=_new_schedule_payload())
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
