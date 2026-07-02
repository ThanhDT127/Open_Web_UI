## Why

Quota is a billing-control boundary, but the current period-reset and alert paths can use or persist inconsistent values. The reported `adminrd` alert illustrates the problem: the notification on June 3, 2026 used the database limit `0.008 USD` and rounded it to `$0.01`, while the dashboard was expected to show a different configured limit.

The system must guarantee that quota limits, usage, reset state, dashboard values, and alert messages all come from the same committed database state before the platform is expanded to more users.

## What Changes

- Make weekly and monthly quota reset atomic and persist the new period state before usage is checked or incremented.
- Make quota limit and usage updates single-user database operations instead of full-user-list read/modify/write operations.
- Make alert evaluation read the latest committed quota state for exactly one user.
- Store alert snapshots with full numeric precision and format displayed currency consistently without changing the underlying value.
- Prevent duplicate threshold alerts when multiple requests finish concurrently.
- Reset threshold alert markers only when the quota period changes.
- Ensure dashboard quota values and alert values use the same database source.
- Add tests covering reset boundaries, concurrent usage updates, limit changes, alert thresholds, rounding, and duplicate prevention.

## Capabilities

### New Capabilities

- `quota-period-reset`: Atomic and persistent weekly/monthly quota period transitions.
- `quota-alert-consistency`: Consistent quota alert calculation, snapshots, formatting, and duplicate prevention.

### Modified Capabilities

- `single-user-query`: All quota and alert mutations must use safe single-user operations without overwriting concurrent updates.

## Impact

- Affected middleware modules: `llm-mw/core/quota.py`, `llm-mw/core/auth.py`, `llm-mw/core/db.py`, `llm-mw/core/alerting.py`, `llm-mw/core/notification.py`.
- Affected APIs and UI: quota status endpoint, user quota updates, dashboard user quota display, alert notifications and email.
- Affected database state: `mw_users.quota`, `mw_users.alerts_sent`, and potentially notification metadata.
- No provider-facing API behavior changes are intended.
