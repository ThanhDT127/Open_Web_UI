## ADDED Requirements

### Requirement: Attribution of cost to a billing account

The system SHALL attribute every `mw_audit_log` row to exactly one billing account. The billing account is the first path segment of a model's `litellm_params.model` (e.g. `openai`, `gemini`, `vertex_ai`, `anthropic`, `xai`, `openrouter`), keyed by its alias (`model_name`). The mapping `alias → billing account` SHALL be sourced at runtime from LiteLLM's admin `/model/info` endpoint (reachable with the master key the middleware already holds), NOT by reading `litellm_config.yaml` — that file is mounted only into the LiteLLM container, not the middleware. The audit `model` field stores the alias, so attribution is a lookup on that map.

The mapping SHALL be a total partition: any audit `model` value that does not resolve to a known billing account (e.g. a retired alias still present in history) SHALL fall into a catch-all bucket named `other`. Consequently the sum of attributed cost across all billing accounts (including `other`) SHALL equal the total cost over the same window, for any production data.

The billing account is the account actually invoiced, NOT the model brand: a model reached through a gateway SHALL be attributed to the gateway account (e.g. a DeepSeek model routed via OpenRouter attributes to `openrouter`, not `deepseek`).

#### Scenario: Reconciliation holds regardless of models used

- **WHEN** cost is summed per billing account over a window and compared to the total cost over the same window
- **THEN** the two totals are equal, because every row maps to exactly one account and unmatched rows land in `other`

#### Scenario: Gateway model attributes to the paying account

- **WHEN** a model whose `litellm_params.model` is `openrouter/deepseek/deepseek-v4-flash` incurs cost
- **THEN** that cost is attributed to `openrouter`, not `deepseek`

#### Scenario: Retired alias is not lost

- **WHEN** the audit history contains a `model` alias no longer present in `litellm_config.yaml`
- **THEN** its cost is attributed to `other`, and the per-account total still reconciles to the grand total

### Requirement: Prepaid credit accounting per billing account

Provider budgets SHALL be modelled as prepaid credit, not a calendar-monthly cap. For each billing account the system SHALL track a `deposited` amount and a `funded_at` timestamp marking the most recent top-up. `deposited` is the credit **baseline as of `funded_at`** (the value spend counts down from), NOT the lifetime total ever deposited — a top-up carries the unspent balance forward and resets `funded_at` (see the settings capability). The system SHALL compute:

- `spent` = SUM(`cost_usd`) over `mw_audit_log` for that account WHERE `ts >= funded_at`.
- `remaining` = `deposited` − `spent`.
- `used_percent` = `spent` / `deposited` × 100 (guarded: `deposited <= 0` yields `0`).

The system SHALL NOT reset any of these on a calendar boundary; the only reset point is a new top-up (which advances `funded_at`).

#### Scenario: Spend is measured from the last top-up, not month start

- **WHEN** an account was topped up on the 3rd and requests were made both before and after that date
- **THEN** `spent` counts only cost with `ts >= funded_at` (the 3rd), ignoring the calendar month boundary

#### Scenario: Zero or missing deposit is guarded

- **WHEN** an account has `deposited <= 0`
- **THEN** `used_percent` is `0` and `remaining` is reported without a division error

### Requirement: Runway projection until credit is exhausted

For each billing account the system SHALL estimate a runway — the number of days until credit is exhausted at the current burn rate: `burn_rate = spent / days_since_funded_at`, `runway_days = remaining / burn_rate`, where `days_since_funded_at` is the elapsed duration `now − funded_at` in days. There is no calendar-monthly window and no reset boundary in this computation.

When too little time has elapsed since the last top-up to estimate reliably (below a configured minimum), OR when `burn_rate` is `0` (no spend since funding, which would divide by zero), the system SHALL report runway as unavailable rather than a misleadingly large or infinite number. The raw burn rate SHALL NOT be surfaced as its own displayed column; it exists only to derive runway.

#### Scenario: Runway warns before exhaustion

- **WHEN** an account has `remaining = $9` and a burn rate of `$2/day`
- **THEN** the runway is reported as approximately 4-5 days

#### Scenario: Early-post-topup is not over-projected

- **WHEN** fewer than the minimum elapsed days have passed since `funded_at`
- **THEN** runway is reported as unavailable, not an inflated day count

#### Scenario: No spend since funding does not divide by zero

- **WHEN** an account has had no cost since `funded_at` (`burn_rate = 0`)
- **THEN** runway is reported as unavailable, not infinity or a division error

### Requirement: Providers endpoint

The system SHALL expose `GET /v1/_mw/providers`, admin-guarded (mirroring the auth of `/v1/_mw/summary`). It SHALL return, per billing account: `deposited`, `funded_at`, `spent`, `remaining`, `used_percent`, `runway_days` (nullable), and a `status` of `ok` / `warn` / `critical` derived from `used_percent` / runway. An account with no configured credit (in particular the catch-all `other`) SHALL report `spent` only, with `deposited`, `remaining`, `used_percent`, and `runway_days` null. It SHALL include the `other` bucket, account totals (`total_remaining`, `total_spent`), and `total_models`.

The response SHALL reflect the prepaid model and SHALL NOT be scoped by the dashboard global time-range filter; it always reports current credit state.

#### Scenario: Endpoint returns per-account credit state

- **WHEN** an admin requests `/v1/_mw/providers`
- **THEN** the response lists each billing account with deposited, spent-since-funding, remaining, used percent, runway and status, plus totals and `total_models`

#### Scenario: Non-admin is rejected

- **WHEN** a non-admin (no valid admin session/key) requests `/v1/_mw/providers`
- **THEN** the request is rejected, consistent with other `/v1/_mw` admin endpoints

### Requirement: Total Models count

`total_models` SHALL be counted server-side from the same LiteLLM admin metadata used for attribution (`/model/info`), reusing that one call. LiteLLM does NOT define the `*-auto` aliases (they are injected by the middleware's `list_models`), so the admin metadata carries no auto entries to subtract; the count SHALL still defensively exclude any alias present in `_AUTO_MODEL_NAMES`. It SHALL NOT be derived from the user-facing `list_models` (which filters by the caller's `allowed_models` and therefore reports a per-user subset, not the admin total).

#### Scenario: Count reflects real deployed models, not injected autos

- **WHEN** LiteLLM `/model/info` returns N deployed models and none of them is a `*-auto` alias
- **THEN** `total_models` is `N` (nothing subtracted, because the autos never appear in the admin metadata)

### Requirement: Provider budget alert uses the shared attribution and prepaid semantics

The per-provider budget alert (CHECK 2, `_check_provider_budget_alerts`) SHALL use the same billing-account attribution and prepaid `spent`/`remaining` computation as the dashboard, so alert numbers and dashboard numbers never diverge. Its trigger condition SHALL express credit exhaustion (low remaining / short runway → "top up") rather than percentage of a monthly budget, and it SHALL NOT use a `date_trunc('month')` window.

This requirement SHALL NOT alter the per-user quota alert (CHECK 1): user quota evaluation, per-user emails, `mw_users.quota`, and `alerts_sent` deduplication remain unchanged.

#### Scenario: Alert and dashboard agree

- **WHEN** the same account's spend is computed for the alert and for the dashboard at the same moment
- **THEN** both use the shared attribution+prepaid function and report the same `spent` and `remaining`

#### Scenario: User quota alert is untouched

- **WHEN** this change is applied
- **THEN** the per-user quota alert path (CHECK 1) still fires on the user's admin-granted quota, sends the user email, and dedupes via `alerts_sent`, with no behavioral change
