# Fix Batch 1 Report — Notifications Branch

## FIX 1 — Model B: effective_horizon unifies inbox + prune

### Files changed
- `backend/app/services.py` lines 29–40: added `effective_horizon()` helper after `materialization_horizon()`
- `backend/app/services.py` line 431 (update_schedule): `materialization_horizon` → `effective_horizon`
- `backend/app/routers/inbox.py` lines 27–29: compute `ceiling = services.effective_horizon(cfg, today)` first, then pass it as `horizon=ceiling` to `materialize_occurrences`

### Tests added
**RED → GREEN evidence** (tests failed before the fix, pass after)

`backend/tests/test_api.py`:
- `test_inbox_shows_occurrence_within_reminder_window` — notify_enabled=True, lead=5, lookahead=0: occurrence at today+3 now appears in inbox ✅
- `test_inbox_hides_occurrence_beyond_lookahead_when_notifications_off` — notify_enabled=False, lookahead=0: occurrence at today+3 stays hidden ✅

`backend/tests/test_services.py`:
- `test_update_schedule_preserves_occurrence_in_reminder_window` — lead=5>lookahead=0, behavior-preserving edit: occurrence+NotificationLog at today+3 survive ✅
- `test_update_schedule_still_prunes_occurrence_not_in_new_rule` — occurrence the new rule genuinely drops is still pruned along with its log ✅

### Existing tests updated
None — all existing `update_schedule` tests use config with `notify_enabled=False` (default), so `effective_horizon` collapses to `materialization_horizon` and behavior is identical.

---

## FIX 2 — F4: scheduler passes tz-aware datetime

### File changed
- `backend/app/notify/scheduler.py` line 50: `datetime.datetime.now()` → `_now_in_tz(cfg.notify_timezone)`

### Tests added
`backend/tests/test_notify_scheduler.py`:
- `test_notification_tick_passes_tz_aware_datetime` — mocks Session/should_run_now/run_due_reminders; asserts received datetime has non-None tzinfo matching configured tz ✅

### Existing tests updated
None — existing scheduler tests cover `should_run_now`, not `notification_tick` directly.

---

## FIX 3 — F5: log dedup row on any bool result

### File changed
- `backend/app/notify/reminders.py` lines 73–79: `if ok is True:` split into `if isinstance(ok, bool):` (log) and inner `if ok is True:` (increment sent)

### Tests added
`backend/tests/test_notify_reminders.py`:
- `test_false_result_logged_and_not_retried` — channel returning False: sent=0, NotificationLog written, second run skips the channel ✅

### Existing tests updated
None — `test_failed_channel_not_logged_and_retried` uses a string `"err"` result; `isinstance("err", bool)` is False, so behavior is unchanged. Test still passes as-is.

---

## Full pytest -q result

```
........................................................................ [ 29%]
........................................................................ [ 58%]
........................................................................ [ 88%]
.............................                                            [100%]
245 passed, 1 warning in 5.37s
```

239 original tests + 6 new tests. No frontend files touched.
