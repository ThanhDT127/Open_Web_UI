## ADDED Requirements

### Requirement: Access metrics carry period-comparison badges

The access tab's request total, its three error groups and its latency percentile SHALL each carry a period-comparison badge, obtained through the existing shared comparison loader rather than through a mechanism built for this tab.

An empty comparison window SHALL yield an absent value, never zero. A loader that reports zero for a window containing no data produces a division by zero in the delta, and the badge then displays a fabricated increase on every load — an error with no symptom on screen beyond a plausible-looking number.

A comparison window whose sample falls below the metric's declared minimum SHALL yield no badge. A period too thin to colour is equally too thin to serve as a baseline, and this restriction applies to the compared window as well as to the current one.

#### Scenario: An empty comparison window shows no delta

- **WHEN** the compared window contains no access records
- **THEN** the badge reports the comparison as unavailable rather than as a change from zero

#### Scenario: A thin comparison window is not used as a baseline

- **WHEN** the compared window's sample falls below the metric's declared minimum
- **THEN** no badge is shown for that metric, and the reason is the sample size rather than an absence of data
