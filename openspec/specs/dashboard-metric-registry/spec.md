# dashboard-metric-registry Specification

## Purpose
TBD - created by archiving change dashboard-period-compare. Update Purpose after archive.
## Requirements
### Requirement: Central metric declaration

Every scorecard metric that appears on the dashboard SHALL be declared exactly once in a central registry. Each declaration SHALL carry, at minimum: the display label, the value format, the delta format, the colour polarity, and whether the metric is eligible for period comparison.

Card rendering code SHALL read these attributes from the registry rather than hard-coding labels, number formatting, or colour logic at each call site.

#### Scenario: A metric is declared once and reused

- **WHEN** the same metric appears on two different tabs
- **THEN** both cards derive their label, formatting and delta behaviour from the one registry entry, so the two cards cannot disagree

#### Scenario: Renaming a metric touches one place

- **WHEN** a metric's display label is changed
- **THEN** the change is made in the registry entry alone, and every card showing that metric picks up the new label without further edits

### Requirement: Three delta formats

The registry SHALL support three delta formats, and each metric SHALL declare which one applies:

- **Relative** — `(current − previous) / previous × 100`, rendered as a percentage. Used for count and money metrics.
- **Percentage point** — `current − previous`, rendered in percentage points. Used for metrics that are themselves percentages, so that a change from 62% to 65% is not misreported as "+4.8%".
- **Absolute** — `current − previous`, rendered as a plain count. Used for small headcount-style metrics.

#### Scenario: Money metric uses relative delta

- **WHEN** total cost moves from `$349.88` to `$412.86`
- **THEN** the badge reports `▲ +18%` with the compared absolute value alongside

#### Scenario: Percentage metric uses percentage points

- **WHEN** the adoption rate moves from `62%` to `68%`
- **THEN** the badge reports `▲ +6 điểm %`, not `▲ +9.7%`

#### Scenario: Headcount metric uses absolute delta

- **WHEN** the count of dormant accounts moves from `66` to `59`
- **THEN** the badge reports `▼ −7`

### Requirement: Colour polarity

Each metric SHALL declare whether an increase is good, an increase is bad, or the direction carries no judgement. The badge SHALL colour each delta line from this declaration rather than from the sign of the number.

Metrics that are administrative counts SHALL declare neutral polarity so that a rise is not coloured as success.

#### Scenario: A rise that is bad is coloured as bad

- **WHEN** total cost increases
- **THEN** the delta line uses the negative colour, because cost declares that an increase is bad

#### Scenario: A rise that is good is coloured as good

- **WHEN** the count of active users increases
- **THEN** the delta line uses the positive colour

#### Scenario: An administrative count is neutral

- **WHEN** the number of accounts provisioned during the period increases
- **THEN** the delta line uses the neutral colour, because provisioning is an administrative act rather than a performance signal

### Requirement: Comparison blocked for metrics outside the time window

A metric whose underlying value is not scoped to the selected time range SHALL declare itself ineligible for comparison, and the renderer SHALL NOT attach a comparison badge to it.

This SHALL include, at minimum, metrics computed from a whole-table snapshot rather than from a windowed query, together with inventory and configuration figures such as total accounts, total models, unit counts and configured budgets.

#### Scenario: Snapshot metric never shows a delta

- **WHEN** a metric is sourced from a query that takes no time bounds and therefore returns the same value for the current, previous and year-ago windows
- **THEN** the registry marks it ineligible and the card renders with no comparison badge, rather than displaying a badge permanently reading zero change

#### Scenario: Inventory card renders without a badge

- **WHEN** a card shows a configured budget or a total account count
- **THEN** no comparison badge is attached

### Requirement: Value formatting from the registry

The registry SHALL declare how each metric's value is formatted — currency, percentage, duration, or plain number — and both the primary value and the comparison values SHALL use that same formatter.

#### Scenario: Comparison value matches the primary format

- **WHEN** a currency metric displays `$412.86`
- **THEN** the compared value in the badge is rendered as `$349.88`, using the same currency formatting rather than a raw number

