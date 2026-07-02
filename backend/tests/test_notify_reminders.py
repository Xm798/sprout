import datetime
from unittest.mock import patch

from sqlmodel import select

from app.models import Schedule, Occurrence, NotificationLog
from app.notify import reminders


def _setup(session, config, lead=3):
    config.notify_enabled = True
    config.notify_lead_days = lead
    config.notify_channels = [
        {"id": "id-ios", "name": "ios", "url": "bark://h/k", "enabled": True},
        {"id": "id-off", "name": "off", "url": "tgram://t/c", "enabled": False},
    ]
    session.add(Schedule(name="rent", interval_unit="month", interval_count=1,
                         anchor_date=datetime.date(2026, 6, 9), status="active",
                         postings=[{"id": "m", "account": "Ex", "amount": "100.00",
                                    "currency": "USD", "cost": None, "price": None}]))
    session.commit()


def test_sends_to_enabled_channels_within_window_and_logs(session, config):
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)   # 6/9 occurrence is within 3-day lead
    with patch("app.notify.reminders.send_to_channels",
               return_value={"ios": True}) as send:
        n = reminders.run_due_reminders(session, config, now)
    assert n == 1
    send.assert_called_once()                          # only the enabled channel
    assert [c["name"] for c in send.call_args.args[0]] == ["ios"]
    logs = session.exec(select(NotificationLog)).all()
    assert len(logs) == 1 and logs[0].channel_id == "id-ios"


def test_dedup_does_not_resend_logged_channel(session, config):
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}):
        reminders.run_due_reminders(session, config, now)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}) as send2:
        n2 = reminders.run_due_reminders(session, config, now)
    assert n2 == 0
    send2.assert_not_called()


def test_failed_channel_not_logged_and_retried(session, config):
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": "err"}):
        reminders.run_due_reminders(session, config, now)
    assert session.exec(select(NotificationLog)).all() == []   # failure: no log row
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}) as retry:
        n = reminders.run_due_reminders(session, config, now)
    assert n == 1
    retry.assert_called_once()                                  # retried next run


def test_renamed_channel_does_not_refire(session, config):
    """Dedup keys on the stable channel id, so renaming a channel (same id,
    new name) must NOT re-send already-reminded occurrences."""
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}):
        reminders.run_due_reminders(session, config, now)
    config.notify_channels[0]["name"] = "apple"          # rename, id unchanged
    session.add(config)
    session.commit()
    with patch("app.notify.reminders.send_to_channels") as send2:
        n2 = reminders.run_due_reminders(session, config, now)
    assert n2 == 0
    send2.assert_not_called()


def test_recreated_channel_with_same_name_fires_again(session, config):
    """A brand-new channel that happens to reuse an old name has a new id and
    must NOT inherit the old channel's dedup rows."""
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": True}):
        reminders.run_due_reminders(session, config, now)
    config.notify_channels[0] = {"id": "id-new", "name": "ios",
                                 "url": "bark://h2/k2", "enabled": True}
    session.add(config)
    session.commit()
    with patch("app.notify.reminders.send_to_channels",
               return_value={"ios": True}) as send2:
        n2 = reminders.run_due_reminders(session, config, now)
    assert n2 == 1
    send2.assert_called_once()


def test_false_result_logged_and_not_retried(session, config):
    """A channel returning False (sent but unsuccessful response) is logged for
    dedup so it is NOT re-sent on the next tick.  Successful send count stays 0."""
    _setup(session, config, lead=3)
    now = datetime.datetime(2026, 6, 8, 9, 0)
    with patch("app.notify.reminders.send_to_channels", return_value={"ios": False}):
        n = reminders.run_due_reminders(session, config, now)
    assert n == 0                                               # not a successful send
    logs = session.exec(select(NotificationLog)).all()
    assert len(logs) == 1 and logs[0].channel_id == "id-ios"   # but dedup row written
    # Second run: channel already logged — must not resend
    with patch("app.notify.reminders.send_to_channels") as send2:
        reminders.run_due_reminders(session, config, now)
    send2.assert_not_called()


def test_loan_reminder_includes_installment_amount(session, config):
    """Loan postings carry roles, not static amounts — the reminder amount must
    come from the occurrence's amortization row, shown as a positive outflow."""
    from app import services

    config.notify_enabled = True
    config.notify_lead_days = 3
    config.notify_channels = [
        {"id": "id-ios", "name": "ios", "url": "bark://h/k", "enabled": True},
    ]
    sch = Schedule(
        name="HomeLoan", narration="Loan installment", kind="loan", status="active",
        loan={"principal": "120000", "annual_rate": "0.05",
              "term_count": 24, "method": "equal_payment"},
        postings=[
            {"id": "p", "account": "Liabilities:Loan", "role": "principal",
             "currency": "CNY", "amount": None, "cost": None, "price": None},
            {"id": "i", "account": "Expenses:Interest", "role": "interest",
             "currency": "CNY", "amount": None, "cost": None, "price": None},
            {"id": "c", "account": "Assets:Bank", "role": "payment",
             "currency": "CNY", "amount": None, "cost": None, "price": None},
        ],
        interval_unit="month", interval_count=1,
        anchor_date=datetime.date(2026, 1, 1), events=[], tags="",
    )
    session.add(sch)
    session.commit()
    session.refresh(sch)
    expected = services._loan_table(sch)[0].payment    # first installment outflow

    now = datetime.datetime(2025, 12, 30, 9, 0)        # 2026-01-01 within 3-day lead
    with patch("app.notify.reminders.send_to_channels",
               return_value={"ios": True}) as send:
        n = reminders.run_due_reminders(session, config, now)
    assert n == 1
    body = send.call_args.args[2]
    assert f"{expected} CNY" in body
