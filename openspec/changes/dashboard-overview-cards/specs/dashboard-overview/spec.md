## ADDED Requirements

### Requirement: Overview tab shell

The dashboard SHALL provide a new top-level tab `🎯 Overview` alongside the existing tabs, without removing or reordering any of the 11 current tabs (including `📚 Knowledge`).

The tab SHALL follow the established convention: a `.tab` button invoking `window.dashboardAPI.switchTab(event, 'overview')`, a panel `<div id="overviewTab" class="tab-content">`, a dedicated JS module `overview.js` exposing `window.overviewAPI`, imported and wired in `main.js` and `tabs.js`.

#### Scenario: Overview tab is present and selectable

- **WHEN** the dashboard loads and the admin clicks the `🎯 Overview` tab
- **THEN** the `overviewTab` panel becomes active and its 6 cards render, while all other tabs remain present and functional

#### Scenario: Knowledge tab preserved

- **WHEN** the Overview tab is added
- **THEN** the `📚 Knowledge` tab and the other 10 existing tabs remain in the tab bar unchanged

### Requirement: Overview executive cards

The Overview tab SHALL display 6 cards. Four cards SHALL show real values sourced by reuse of existing data:

- **Cost MTD** — total cost from the first day of the current month to now.
- **CSAT** — customer satisfaction percent.
- **System Health** — error rate percent and P95 latency (uptime line omitted until a later phase).
- **Cost Concentration** — the percentage of total cost incurred by the top 10% of users.

Two cards SHALL render an explicit placeholder (e.g. `—`) with a hint that the metric arrives in a later phase:

- **Adoption rate** — used / granted accounts.
- **Cost / active user**.

Each card SHALL label its time window so the fixed-month scope of Cost MTD is not confused with the range-scoped cards.

#### Scenario: Real cards show values

- **WHEN** the Overview tab renders with available data
- **THEN** Cost MTD, CSAT, System Health, and Cost Concentration display numeric values with color thresholds

#### Scenario: Placeholder cards

- **WHEN** the Overview tab renders and Phase 4 metrics are not yet available
- **THEN** the Adoption rate and Cost / active user cards show a placeholder with a hint indicating the metric is pending

### Requirement: Overview time-window scoping

Cost MTD SHALL always be computed for the current calendar month regardless of the dashboard's global time-range filter. CSAT, System Health, and Cost Concentration SHALL follow the dashboard's global time-range filter.

#### Scenario: Cost MTD ignores global range

- **WHEN** the admin changes the global time-range filter
- **THEN** Cost MTD still reflects month-to-date, while CSAT, System Health, and Cost Concentration recompute for the selected range

### Requirement: Reuse of summary data without duplicate fetch

The Overview cards for System Health and Cost Concentration SHALL reuse the summary response already fetched for the global range (via an accessor exported from `usage.js`) instead of issuing a duplicate summary request. Cost MTD SHALL fetch the summary API with a month-to-date range; CSAT SHALL use the existing satisfaction analytics data.

#### Scenario: No duplicate summary fetch for global-range cards

- **WHEN** the Overview tab renders System Health and Cost Concentration
- **THEN** they read the cached global-range summary rather than re-requesting the summary endpoint

### Requirement: Cost concentration metric in summary API

The summary API SHALL expose a `top10_pct_cost_share` value in its `totals`, computed over the full set of users in the range before any top-N truncation, representing the share of total cost attributable to the top 10% of users by cost.

#### Scenario: Concentration computed over full population

- **WHEN** the summary is computed for a range with more than 20 users
- **THEN** `top10_pct_cost_share` reflects all users (not only the top 20 returned in `breakdown_by_user`)

#### Scenario: Degenerate populations

- **WHEN** the range has zero users or a single user
- **THEN** `top10_pct_cost_share` returns a well-defined value (0 when no cost; 100 when a single user holds all cost) without error
