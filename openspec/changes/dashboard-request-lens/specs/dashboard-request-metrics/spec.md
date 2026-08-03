## ADDED Requirements

### Requirement: Latency percentiles P50, P99 and maximum

The summary aggregation SHALL expose `p50_latency_ms`, `p99_latency_ms` and `max_latency_ms` in `totals`, alongside the existing `p95_latency_ms`. All four SHALL be derived from the same latency array over the same request population, so the percentiles are mutually consistent.

When the window contains no latency samples, each percentile field SHALL be `null` rather than `0`.

#### Scenario: Percentiles come from one shared population

- **WHEN** the window has latency samples and P95 is computed
- **THEN** P50, P99 and max are read from the same sorted array, and `p50_latency_ms ≤ p95_latency_ms ≤ p99_latency_ms ≤ max_latency_ms`

#### Scenario: Index never runs off the end of the array

- **WHEN** the sample count is small enough that `int(n × 0.99)` equals `n`
- **THEN** the P99 value falls back to the last element instead of raising an out-of-range error, mirroring the existing P95 guard

#### Scenario: No latency data

- **WHEN** the window contains no completed requests with a latency value
- **THEN** `p50_latency_ms`, `p99_latency_ms` and `max_latency_ms` are all `null`

### Requirement: Unit cost economics

The summary aggregation SHALL expose `cost_per_request` and `cost_per_1k_tokens` in `totals`. `cost_per_request` SHALL divide `total_cost` by `requests_ok`; `cost_per_1k_tokens` SHALL divide `total_cost` by `total_tokens` (×1000). The denominator SHALL be `requests_ok`, not `requests_total`, because `total_cost` and `total_tokens` are accumulated over successful requests only — dividing a successful-only numerator by an all-requests denominator would mix populations and understate the true unit cost.

A zero denominator SHALL NOT produce a division error; the metric SHALL report `0` (or `null`) instead of infinity or NaN.

#### Scenario: Normal computation

- **WHEN** the window has `requests_ok = 200`, `total_cost = 12.0` and `total_tokens = 600000`
- **THEN** `cost_per_request = 0.06` and `cost_per_1k_tokens = 0.02`

#### Scenario: Zero denominator is guarded

- **WHEN** the window has `requests_ok = 0` (or `total_tokens = 0`)
- **THEN** the corresponding metric is `0`/`null`, never infinity or NaN

### Requirement: Token intensity

The summary aggregation SHALL expose `avg_tokens_per_request` and `tokens_in_out_ratio` in `totals`. The aggregation SHALL sum `tokens_in` and `tokens_out` per window (new accumulators), since the loop currently sums only `tokens_total`. `avg_tokens_per_request` SHALL divide `total_tokens` by `requests_ok`, the same successful-request population the token sums are drawn from.

The in:out ratio SHALL guard against a zero output-token denominator.

#### Scenario: Averages and ratio computed

- **WHEN** the window sums to `tokens_in = 400000` and `tokens_out = 200000` across `requests_ok = 200`
- **THEN** `avg_tokens_per_request = 3000` and `tokens_in_out_ratio = 2.0`

#### Scenario: Zero output tokens

- **WHEN** the window has `total_tokens_out = 0`
- **THEN** `tokens_in_out_ratio` is reported without a division-by-zero (e.g. `null` or `0`)

### Requirement: Throughput average and peak

The summary aggregation SHALL expose `rpm_avg` and `rpm_peak` in `totals`, **both expressed as requests per minute** so the two figures are directly comparable on the same scorecard. `rpm_avg` SHALL be `requests_total` divided by the window length in minutes derived from the resolved `[cutoff, end_time]`. `rpm_peak` SHALL be the busiest time-series bucket's request count divided by that bucket's length in minutes.

When time-series buckets are coarser than one minute (hourly or daily on longer ranges) `rpm_peak` is a within-bucket average and therefore smooths sub-bucket spikes; the aggregation SHALL also expose `rpm_peak_bucket` (the bucket granularity) so the reader knows the resolution behind the peak. The identity of the busiest period is already available from the existing hour-of-day activity data and SHALL NOT be duplicated here.

#### Scenario: Average over the window

- **WHEN** the window is 60 minutes long with `requests_total = 120`
- **THEN** `rpm_avg = 2.0`

#### Scenario: Peak normalised to the same unit as the average

- **WHEN** buckets are hourly and the busiest hour holds `120` requests
- **THEN** `rpm_peak = 2.0` (120 ÷ 60 minutes), the same requests-per-minute unit as `rpm_avg`, and `rpm_peak_bucket` reports `hour`

### Requirement: Queue health

The summary aggregation SHALL expose the open pending count (`pending_open_count`, already present) together with `pending_oldest_age_sec`, the age in seconds of the oldest still-open pending request, derived from the minimum `ts` in `mw_pending`. The `ts` unit SHALL be confirmed before the subtraction so the age is not off by a factor of 1000.

When there are no open pending requests, `pending_oldest_age_sec` SHALL be `null`.

#### Scenario: Oldest age from the earliest pending row

- **WHEN** `mw_pending` holds open rows and the earliest has timestamp `T`
- **THEN** `pending_oldest_age_sec = now − T`, expressed in seconds

#### Scenario: No pending requests

- **WHEN** there are no open pending rows
- **THEN** `pending_oldest_age_sec` is `null`

### Requirement: Comparison eligibility of request-lens metrics

Request-lens metrics that are scoped to the selected time window SHALL be eligible for period comparison and SHALL reuse the existing metric-registry and period-comparison mechanisms without changing them. Whole-table snapshot metrics SHALL be declared ineligible for comparison.

`pending_open_count` and `pending_oldest_age_sec` are whole-table snapshots, not scoped to the selected window, and therefore SHALL be declared `compare: false`.

#### Scenario: Windowed metric shows a comparison badge

- **WHEN** `cost_per_request` is rendered for a selected range
- **THEN** it carries a KT/CK comparison badge produced by the existing period-comparison mechanism

#### Scenario: Snapshot metric shows no comparison badge

- **WHEN** `pending_oldest_age_sec` is rendered
- **THEN** no comparison badge is attached, because the value is a whole-table snapshot rather than a windowed figure
