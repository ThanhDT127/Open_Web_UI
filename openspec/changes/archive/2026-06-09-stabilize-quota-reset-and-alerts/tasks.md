## 1. Diagnose and Protect Existing Data

- [x] 1.1 Add a diagnostic query/report that compares persisted quota limits, dashboard API responses, and recent alert snapshots for each user
- [x] 1.2 Confirm and document why `adminrd` remains persisted with `limit_cost_usd=0.008` while the dashboard was expected to show `10`
- [x] 1.3 Add regression fixtures for small limits, changed limits, expired period anchors, and existing alert markers

## 2. Implement Atomic Quota Period Reset

- [x] 2.1 Replace the `_prev_period_start` reset check with a targeted database reset operation
- [x] 2.2 Reset period counters, period anchor, and alert eligibility for one user in one transaction
- [x] 2.3 Ensure chat, embeddings, images, quota status, and alert evaluation perform reset before reading current-period usage
- [x] 2.4 Add weekly and monthly boundary tests across configured timezones

## 3. Remove Unsafe Full-User Mutations

- [x] 3.1 Replace alerting `load_users()` plus `save_users()` mutation with targeted single-user operations
- [x] 3.2 Replace administrative quota-limit updates with targeted updates that preserve concurrent usage counters
- [x] 3.3 Audit remaining `save_users()` callers and ensure request-time or concurrent paths cannot overwrite usage
- [x] 3.4 Add concurrency tests proving simultaneous usage, reset, alert, and limit updates do not lose data

## 4. Make Alerts Consistent and Deduplicated

- [x] 4.1 Add additive database storage or an equivalent unique claim for user, period, threshold, and alert type
- [x] 4.2 Evaluate alerts from a fresh committed single-user quota record after usage is persisted
- [x] 4.3 Store exact alert-time usage, limit, percentage, threshold, and period anchor in notification metadata
- [x] 4.4 Prevent duplicate notifications and emails when concurrent requests cross the same threshold
- [x] 4.5 Reset alert eligibility only as part of a committed quota-period transition

## 5. Align Dashboard and Message Formatting

- [x] 5.1 Make user quota update APIs return the committed database record after saving
- [x] 5.2 Make dashboard quota values and quota alerts use the same database fields
- [x] 5.3 Use adaptive currency formatting for small values and clamp displayed remaining amount to zero
- [x] 5.4 Add UI/API tests for saving `10`, `0.1`, `0.01`, and `0.008` USD limits

## 6. Backup Snapshot and Verification

- [x] 6.1 Add an explicit database-to-JSON user snapshot operation outside the request hot path
- [x] 6.2 Update documentation to describe PostgreSQL as runtime source and JSON as generated snapshot
- [x] 6.3 Run middleware quota and alert regression tests
- [x] 6.4 Perform a controlled manual verification using a test user at 80, 95, and 100 percent thresholds
