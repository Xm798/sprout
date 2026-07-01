# Simplify Fixes Report

## FIX 1 — `backend/app/main.py`: capture env gate once

**Changed:** `main.py:20-27`
- Added `enabled = _scheduler_enabled()` local before the `if` guard.
- Both `_scheduler.start()` and `_scheduler.shutdown()` now test `enabled` instead of calling `_scheduler_enabled()` twice.

## FIX 2 — `backend/app/services.py`: extract `_delete_occurrences` helper

**Changed:** `services.py:29-44` (new helper), `services.py:456-462` (delete_schedule), `services.py:430-440` (update_schedule)
- Added `_delete_occurrences(session, occurrences)` after `materialization_horizon` (see FIX 4). Fetches all NotificationLog rows for the batch with a single `IN` query, deletes them, then deletes the occurrences.
- `delete_schedule`: replaced the per-occurrence log-deletion loop with `_delete_occurrences(session, list(occs))`.
- `update_schedule`: pre-collects stale occurrences into `stale = [...]`, calls `_delete_occurrences(session, stale)` once, then continues the loop with a `continue` guard for stale rows (same predicate, no behavioral change).

## FIX 3 — `backend/app/notify/reminders.py`: batch dedup + schedule lookups

**Changed:** `reminders.py:49-69`
- Before the `for occ in due:` loop: one `IN` query fetches all NotificationLog rows for the due batch; result is indexed into `already_by_occ: dict[int, set[str]]`.
- Before the loop: one `IN` query fetches all schedules for the due batch; result indexed into `sch_by_id`.
- Inside the loop: `already = already_by_occ.get(occ.id, set())` and `sch = sch_by_id.get(occ.schedule_id)` replace per-occurrence DB calls.
- All per-occurrence try/except, commit, log writes unchanged.

## FIX 4 — rename `_materialization_horizon` → `materialization_horizon`

**Changed:** `services.py:29` (definition), `services.py:52` and `services.py:432` (internal callers), `routers/inbox.py:29`
- Dropped leading underscore to make the function part of the module's public API.
- `inbox.py`: replaced `ceiling = today + datetime.timedelta(days=cfg.lookahead_days)` with `ceiling = services.materialization_horizon(cfg, today)`. The `datetime.timedelta` import in inbox.py is still used for other type annotations so it remains.

## FIX 5 — `backend/app/routers/meta.py`: reuse `enabled_channels`

**Changed:** `meta.py:11` (new import), `meta.py:128-132` (test_notifications)
- Added `from app.notify.reminders import enabled_channels`.
- `test_notifications`: the "no channel_name" branch now calls `chans = enabled_channels(cfg)` instead of re-implementing the filter inline. The named-channel branch was restructured to a single-pass filter `[c for c in ... if c.get("url") and c["name"] == body.channel_name]`.

## FIX 6 — `backend/tests/test_notify_reminders.py`: dedup test setup

**Changed:** `test_notify_reminders.py:48-54`
- `test_failed_channel_not_logged_and_retried`: removed the 6-line inline config+schedule setup, replaced with `_setup(session, config, lead=3)`.
- The `_setup` helper adds a second disabled channel ("off") and a schedule with postings; the disabled channel is filtered by `enabled_channels`, so "ios" is still the only exercised channel. All assertions pass unchanged.

## FIX 7 — `backend/tests/test_services.py`: extract `_occ_with_log` fixture helper

**Changed:** `test_services.py:576-585` (new helper + both cascade-delete tests)
- Added `_occ_with_log(session, config, today) -> tuple` returning `(sch, occ, nl.id)`.
- Both `test_delete_schedule_removes_notification_logs` and `test_update_schedule_removes_notification_log_for_pruned_occurrence` now call `sch, occ, nl_id = _occ_with_log(session, config, today)`. Assertions unchanged.

## SKIPPED items

None of the SKIP items were applied.

## Test Results

- **Backend:** `pytest -q` → 239 passed, 1 warning (5.06s)
- **Frontend:** `npm run test` → 66 passed across 13 test files
- **Lint:** `npm run lint` (tsc --noEmit) → clean (no output)
