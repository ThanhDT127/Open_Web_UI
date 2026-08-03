## ADDED Requirements

### Requirement: A comparison window is cached under the filters it was fetched with

Comparison responses are cached per endpoint and window. Where a caller narrows the comparison with additional filters, those filters SHALL form part of the cache key.

Without this, changing a tab-local filter is served the previous filter's response, and the badge compares one selection's present against another selection's past with nothing on screen revealing it. The key SHALL be stable regardless of the order the filters were supplied, and SHALL be unchanged in form for callers that supply none, so existing callers keep their behaviour.

#### Scenario: Two filter selections do not share a cached response

- **WHEN** the same endpoint and window are requested under two different filter selections
- **THEN** each selection resolves to its own response

#### Scenario: Callers without filters are unaffected

- **WHEN** a caller supplies no filters
- **THEN** its cache key is identical to the one used before filters were keyed

### Requirement: A comparison baseline meets the same minimum sample as the current window

A period whose sample is too thin to colour is equally too thin to serve as the baseline of a trend. Where a metric declares a minimum sample, the comparison window SHALL be held to that minimum as well as the current window, and SHALL report no value when it falls short.

Metrics compared from the same response SHALL be gated on their own denominators, because those denominators thin out independently.

#### Scenario: A thin baseline yields no delta

- **WHEN** the current window meets a metric's minimum but the compared window does not
- **THEN** that period's line reports no value rather than a percentage-point change

#### Scenario: Two metrics from one response are gated separately

- **WHEN** one metric's denominator meets the minimum in the compared window and another's does not
- **THEN** only the metric that falls short loses its comparison
