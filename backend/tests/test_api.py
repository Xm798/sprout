import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.main import app
from app.db import get_session
from app.config import AppConfig


@pytest.fixture
def client(tmp_path):
    demo = Path(__file__).parent / "fixtures" / "demo.bean"
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
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


def _new_schedule_payload():
    return {
        "name": "Spotify", "narration": "sub", "amount": "15.00", "currency": "USD",
        "from_account": "Assets:CreditCard", "to_account": "Expenses:Subscription",
        "interval_unit": "month", "interval_count": 1,
        "anchor_date": "2026-01-15", "max_count": 6, "tags": "sprout",
    }


def test_create_and_list_schedules(client):
    r = client.post("/schedules", json=_new_schedule_payload())
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.get("/schedules").json()[0]["id"] == sid


def test_inbox_lists_pending(client):
    client.post("/schedules", json=_new_schedule_payload())
    r = client.get("/inbox")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["status"] == "pending"


def test_preview_then_confirm(client):
    client.post("/schedules", json=_new_schedule_payload())
    occ_id = client.get("/inbox").json()[0]["id"]
    prev = client.get(f"/inbox/{occ_id}/preview")
    assert "Expenses:Subscription" in prev.json()["text"]
    r = client.post(f"/inbox/{occ_id}/confirm", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"


def test_skip(client):
    client.post("/schedules", json=_new_schedule_payload())
    occ_id = client.get("/inbox").json()[0]["id"]
    r = client.post(f"/inbox/{occ_id}/skip")
    assert r.json()["status"] == "skipped"


def test_accounts_and_currencies(client):
    assert "Assets:CreditCard" in client.get("/accounts").json()
    assert client.get("/currencies").json() == ["USD", "CNY"]


def test_get_and_update_config(client):
    cfg = client.get("/config").json()
    assert cfg["write_mode"] == "single_file"
    r = client.put("/config", json={**cfg, "lookahead_days": 7})
    assert r.json()["lookahead_days"] == 7
