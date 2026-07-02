## Context

Quota state is stored in `mw_users.quota` and alert markers in `mw_users.alerts_sent`. Usage increments are mostly atomic, but quota reset and alert evaluation still use read/modify/write paths that can operate on stale data or overwrite concurrent updates.

The observed `adminrd` notification was created on June 3, 2026 from a limit of `0.008 USD` and usage of `0.0114 USD`. The notification rounded both values to two decimals. The database still contains the `0.008 USD` limit, so a dashboard showing `$10` would indicate a dashboard persistence or data-source mismatch rather than an email arithmetic error.

## Goals / Non-Goals

**Goals:**

- Persist quota period transitions correctly.
- Make database quota state the single source used by enforcement, dashboard, and alerts.
- Prevent concurrent quota or alert operations from overwriting each other.
- Preserve the exact values used to create each alert.
- Make alert formatting understandable for small limits.

**Non-Goals:**

- Redesign provider pricing.
- Add group quotas.
- Change the graceful behavior that allows the current successful request to finish before blocking later requests.

## Decisions

### 1. Reset periods with a targeted database transaction

The middleware will calculate the expected period anchor and update only the target user when the stored anchor is older. Resetting usage and alert markers will happen in the same database transaction.

This replaces the current `_prev_period_start` comparison and full-list save path.

### 2. Keep the database as the runtime source of truth

Quota enforcement, quota status, dashboard values, and alerts will read committed `mw_users` state. JSON files will not be mutated on every hot-path increment; they will be refreshed by an explicit snapshot/backup operation.

This avoids slow and unsafe concurrent file writes while making the backup behavior honest and testable.

### 3. Claim alert thresholds atomically

A dedicated quota alert event record, or an equivalent unique database claim, will identify `(user, period_start, threshold, alert_type)`. Only the request that successfully creates the claim may create the notification or send email.

This is safer than loading and replacing the entire `alerts_sent` object.

### 4. Store alert snapshots separately from live quota

Every created notification will retain the exact `used`, `limit`, percentage, period anchor, and threshold used at alert time. Historical emails do not change when an administrator later changes a limit.

### 5. Format without hiding small values

Alert messages will use sufficient decimal places for values below one dollar and clamp displayed remaining value to zero. Metadata will retain the unrounded numeric values.

## Risks / Trade-offs

- [Existing alert history contains rounded messages] -> Preserve history and apply the new format only to new alerts.
- [Changing JSON backup behavior differs from the old spec] -> Update the single-user-query requirement and provide an explicit database-to-JSON snapshot task.
- [A successful request may take usage beyond the limit] -> Preserve graceful enforcement and block subsequent requests.
- [Schema migration for alert claims] -> Make the migration additive and keep existing notifications readable.

## Migration Plan

1. Add the alert-claim storage and targeted quota reset/update functions.
2. Migrate hot-path alert evaluation to single-user committed reads.
3. Remove full-user-list saves from quota and alert paths.
4. Add database-to-JSON snapshot support.
5. Deploy and verify reset, update, and alert behavior against test users.
6. Preserve existing quota and notification data; rollback by reverting code while leaving additive tables unused.

## Open Questions

- Whether the dashboard should always show four decimal places or use adaptive formatting for limits below one dollar.
