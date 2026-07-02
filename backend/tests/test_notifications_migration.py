"""The notifications migration must apply cleanly to a database that already
has rows (the server_default path). conftest builds schema via create_all and
never exercises Alembic, so this is the only migration coverage."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parent.parent


def test_upgrade_on_populated_db(tmp_path):
    db = tmp_path / "populated.db"
    url = f"sqlite:///{db}"
    env_url = {"SPROUT_DATABASE_URL": url}

    # Bring an empty DB to the PREVIOUS head, then insert a config + occurrence row.
    env = {**os.environ, **env_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "c31530b8db05"],
        cwd=BACKEND, env=env, check=True, capture_output=True,
    )
    eng = sa.create_engine(url)
    with eng.begin() as c:
        c.execute(sa.text(
            "INSERT INTO appconfig (id, ledger_main_file, ledger_root, write_mode, "
            "single_file_name, month_file_template, default_tag, default_currency, "
            "lookahead_days) VALUES (1,'','','single_file','sprout.bean','t','sprout','USD',0)"
        ))
        c.execute(sa.text(
            "INSERT INTO schedule (id, name, payee, narration, interval_unit, "
            "interval_count, anchor_date, tags, status, postings, created_at, updated_at) "
            "VALUES (1,'rent','','','month',1,'2026-01-01','','active','[]','2026-01-01','2026-01-01')"
        ))
        c.execute(sa.text(
            "INSERT INTO occurrence (id, schedule_id, due_date, status, override_amounts) "
            "VALUES (1,1,'2026-02-01','pending','{}')"
        ))
    eng.dispose()

    # The new migration must upgrade to head without crashing on the populated rows.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND, env=env, check=True, capture_output=True,
    )

    eng = sa.create_engine(url)
    insp = sa.inspect(eng)
    cols = {c["name"] for c in insp.get_columns("appconfig")}
    assert {"notify_enabled", "notify_channels", "notify_lead_days",
            "notify_time", "notify_timezone"} <= cols
    assert "notificationlog" in insp.get_table_names()
    eng.dispose()
