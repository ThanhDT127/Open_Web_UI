## ADDED Requirements

### Requirement: Adoption rate

The system SHALL expose an adoption endpoint that reports `adoption_rate_percent` for a selected time window. The denominator SHALL be the count of currently provisioned accounts (`mw_users` where `deleted_at IS NULL`), a point-in-time snapshot. The numerator SHALL be the count of distinct users active in the window (drawn from the full, uncapped `breakdown_by_user` of `compute_usage_summary`) **intersected with the provisioned roster**. Because the audit aggregation does not exclude deleted users, taking the intersection is required so that the numerator cannot contain users absent from the denominator; the rate SHALL therefore always be between 0 and 100.

A zero denominator SHALL NOT produce a division error; the rate SHALL be reported as `0`.

#### Scenario: Numerator is intersected with the current roster

- **WHEN** 45 distinct users are active in the window but 5 of them have been deleted (not in the provisioned roster of 186)
- **THEN** the numerator is 40 (the 40 active users still provisioned), `adoption_rate_percent ≈ 21.5`, and the rate never exceeds 100

#### Scenario: Numerator uses the full population, not the displayed leaderboard

- **WHEN** more than 20 users are active in the window (the Users-tab leaderboard is capped at 20 rows)
- **THEN** the adoption numerator still counts all provisioned active users, computed on the uncapped `breakdown_by_user`, not the 20 rows shown

#### Scenario: Zero provisioned accounts is guarded

- **WHEN** there are no provisioned accounts
- **THEN** `adoption_rate_percent` is `0`, never infinity or NaN

### Requirement: New accounts provisioned in period

The adoption endpoint SHALL expose `new_accounts_in_period`, the count of accounts whose `created_at` falls within `[start, end]`. It SHALL NOT filter by current deletion or active status, so that later deletion or disabling does not systematically shrink past comparison periods. This metric is window-scoped and SHALL be eligible for period comparison. Its label SHALL reflect that `created_at` marks account provisioning (lazy-provision on first auth), not HR hire date.

Because operational deletion is soft (the row is retained with `deleted_at` set), every provisioning event created in a period remains counted for that period indefinitely; the count is stable across time. Hard purge is a non-operational legal-erasure path only and is out of scope for this metric.

#### Scenario: Later deletion does not shrink the period count

- **WHEN** 5 accounts have `created_at` within the window and 2 of those are later soft-deleted (`deleted_at` set)
- **THEN** `new_accounts_in_period = 5`, because the provisioning event occurred inside the window regardless of current deletion status

#### Scenario: Only accounts created inside the window are counted

- **WHEN** an account was created before `start`
- **THEN** it is excluded from `new_accounts_in_period`

### Requirement: Daily and weekly active user series

The adoption endpoint SHALL expose a daily activity series carrying, per day, the number of distinct active users (DAU) and the number of distinct users active within the trailing 7-day window ending that day (WAU). The series SHALL be built at day resolution regardless of the dashboard's automatic bucket size. WAU SHALL be computed as the size of the union of daily user sets and SHALL NOT be derived by summing DAU values, because a user active on multiple days must be counted once.

When the selected range is shorter than one day, the series SHALL be empty.

#### Scenario: WAU deduplicates users across days

- **WHEN** the same user is active on Monday and Tuesday and no one else is active that week
- **THEN** each day's DAU counts that user once for its own day, and WAU for any day in that week counts the user exactly once (not twice)

#### Scenario: DAU never exceeds WAU

- **WHEN** the series is computed for any day
- **THEN** that day's DAU is less than or equal to its WAU, because the single-day active set is a subset of the trailing seven-day active set (the provisioned reference line is a visual guide only and MAY be exceeded by WAU when historical or deleted users were active)

#### Scenario: Sub-day range yields no series

- **WHEN** the selected range is shorter than 24 hours
- **THEN** the activity series is empty and the chart is hidden rather than rendering a meaningless line

### Requirement: Dormant account list

The adoption endpoint SHALL expose a dormant-account list derived from each account's last activity timestamp (`max(ts)` per user in `mw_audit_log`) checked against the provisioned roster. An account SHALL be classified as **never used** when it has no activity rows, and as **stopped** when its last activity is older than a configurable threshold (default 30 days). Each entry SHALL include the account email, provisioning date, last-seen timestamp (or an explicit never-used marker), days since last activity, and the account's active flag. The list is a whole-roster snapshot, not scoped to the selected window, and SHALL be declared ineligible for period comparison.

#### Scenario: Never-used and stopped are distinguished

- **WHEN** account A has no activity rows and account B last acted 45 days ago (threshold 30)
- **THEN** A is listed as never-used and B is listed as stopped, and an account active 5 days ago appears in neither list

#### Scenario: Days-since is computed from provisioning when never used

- **WHEN** a never-used account was provisioned 143 days ago
- **THEN** its days-silent value is 143, measured from `created_at` rather than a null last-seen

### Requirement: Quota utilization histogram

The adoption endpoint SHALL expose a histogram of per-account quota utilization computed as `used_cost_usd / limit_cost_usd` using the same formula as `get_user_quota_status`, bucketed into `0–25`, `25–50`, `50–75`, `75–90` and `>90` percent. Accounts with a non-positive limit SHALL be counted in a separate **unlimited** bucket and SHALL NOT be forced into the `0–25` bucket. The histogram is a roster snapshot and SHALL be declared ineligible for period comparison.

#### Scenario: Unlimited accounts are separated

- **WHEN** an account has `limit_cost_usd = 0`
- **THEN** it is counted in the unlimited bucket, not in `0–25`

#### Scenario: Bucketing follows the quota-status formula

- **WHEN** an account has `used_cost_usd = 8` and `limit_cost_usd = 10`
- **THEN** it falls in the `75–90` bucket (80%)

### Requirement: Cost concentration reuse (Pareto)

The adoption endpoint SHALL reuse the already-computed `top10_pct_cost_share` and the full `breakdown_by_user` from `compute_usage_summary` to drive the Pareto view, and SHALL NOT recompute cost concentration. The `compute_usage_summary` function SHALL NOT be modified by this change.

#### Scenario: Pareto reads existing fields

- **WHEN** the Pareto chart is rendered
- **THEN** its cost-concentration figure equals the `top10_pct_cost_share` already returned by `compute_usage_summary`, computed over the full user population

### Requirement: Overview placeholder cards resolved

The Overview `Tỷ lệ sử dụng` and `Chi phí / người dùng thật` cards, left as placeholders in Phase 1, SHALL display real values sourced from the adoption endpoint. `Chi phí / người dùng thật` SHALL be `cost_total_usd` divided by the count of distinct users active in the window — the raw audit count that also drives the DAU/WAU series, NOT the roster-intersected adoption numerator, since incurred cost is real even for users since deleted. Both operands are reused rather than recomputed, and the metric SHALL guard a zero active-user denominator.

#### Scenario: Cost per active user is guarded

- **WHEN** the window has zero active users
- **THEN** the `Chi phí / người dùng thật` card shows `0`/`—` rather than raising a division error

### Requirement: Comparison eligibility of adoption metrics

Adoption metrics scoped to the selected time window SHALL be eligible for period comparison and SHALL reuse the existing metric-registry and period-comparison mechanisms without changing them. Whole-roster snapshot metrics SHALL be declared ineligible for comparison.

`adoption_rate_percent` and `new_accounts_in_period` are window-scoped and SHALL be comparable. The dormant list, the quota histogram, and the provisioned-account count are whole-roster snapshots and SHALL be declared `compare: false`.

#### Scenario: Windowed adoption metric shows a badge

- **WHEN** `new_accounts_in_period` is rendered for a selected range
- **THEN** it carries a KT/CK comparison badge produced by the existing mechanism

#### Scenario: Snapshot roster metric shows no badge

- **WHEN** the dormant count or quota histogram is rendered
- **THEN** no comparison badge is attached, because the value is a whole-roster snapshot
