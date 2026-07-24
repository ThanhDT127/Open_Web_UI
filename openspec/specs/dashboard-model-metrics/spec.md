# dashboard-model-metrics Specification

## Purpose
TBD - created by archiving change dashboard-model-lens. Update Purpose after archive.
## Requirements
### Requirement: Cost share per model

Each row of `breakdown_by_model` SHALL carry `cost_share_percent`, the model's cost as a percentage of total cost across the whole population: `model_cost / total_cost × 100`. The denominator SHALL be the population-wide `total_cost` local already computed by `compute_usage_summary` (the same total that drives `top10_pct_cost_share`), NOT the sum of the displayed rows. The value SHALL be computed before the endpoint caps the list at 20 rows, so each row reports its true share regardless of truncation.

A zero total cost SHALL NOT produce a division error; the share SHALL be reported as `0`.

#### Scenario: Share is computed against the population total, not the displayed subset

- **WHEN** there are 30 models and `get_summary_v2` returns only the top 20 by cost
- **THEN** each returned row's `cost_share_percent` equals its cost divided by the total cost of all 30 models, so the 20 displayed shares sum to less than 100 (the remaining tail is the untruncated models)

#### Scenario: Zero total cost is guarded

- **WHEN** total cost in the window is `0`
- **THEN** every `cost_share_percent` is `0`, never infinity or NaN

### Requirement: Unique users per model

Each row of `breakdown_by_model` SHALL carry `unique_users`, the count of distinct `user_id` values that issued at least one request to that model within the selected window. It SHALL be accumulated from the same audit loop that builds the existing model breakdown, using the `user_id` already in scope, in **both** the success and error branches — consistent with `requests_total`, which already counts error requests per model. A user whose requests to a model all failed SHALL therefore still be counted in that model's `unique_users`. Because a user active on several models is counted once per model, the sum of `unique_users` across models MAY exceed the count of distinct active users in the window; this is expected and is not a population partition.

#### Scenario: A user of multiple models is counted in each

- **WHEN** one user issues requests to model A and model B, and no one else is active
- **THEN** `unique_users` is 1 for A and 1 for B, and the sum across models (2) exceeds the single distinct active user

#### Scenario: Distinct counting, not request counting

- **WHEN** a single user issues 50 requests to model A
- **THEN** `unique_users` for A is 1, independent of the 50 in `requests_total`

#### Scenario: Error-only user is still counted

- **WHEN** a user's only requests to model A all fail (error status) and never succeed
- **THEN** that user is counted in model A's `unique_users`, matching model A's `requests_total` which also includes those failed requests

### Requirement: Existing model columns and totals are unchanged

This change SHALL add fields only. The existing `breakdown_by_model` fields (`requests_total`, `requests_ok`, `errors`, `error_rate_percent`, `tokens_total`, `cost_usd`, `p95_latency_ms`) and the `totals` object SHALL retain their current values and shapes. The client-side `$/request` figure already rendered by the Usage table (`cost_usd / requests_total`) SHALL NOT be recomputed or altered by this change.

#### Scenario: No regression on existing figures

- **WHEN** the model breakdown is computed before and after this change for the same window
- **THEN** every pre-existing field on each model row is identical, and only `cost_share_percent` and `unique_users` are added

### Requirement: Model-table columns are not period-comparison metrics

`cost_share_percent` and `unique_users` are breakdown-table columns, not scorecards. They SHALL NOT be declared in `metrics_registry.js` and SHALL NOT carry a KT/CK comparison badge, consistent with the Phase 2 rule that only scorecards are wired for period comparison.

#### Scenario: No comparison badge on table columns

- **WHEN** the Top Models table renders the two new columns
- **THEN** no KT/CK badge is attached to them, and `metrics_registry.js` is not consulted for them
