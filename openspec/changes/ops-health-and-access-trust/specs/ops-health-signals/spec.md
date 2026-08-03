## ADDED Requirements

### Requirement: System health is reachable from the dashboard

The health report SHALL be served on a path the dashboard can actually reach, and that path SHALL sit behind the same admin guard as every other dashboard endpoint.

A reverse proxy that has no rule for the health path routes the request to whichever service owns the catch-all rule. That neighbouring service answers with its own health document and its own success status, so the failure is indistinguishable from success at the caller: the response arrives, it is well-formed, and it belongs to a different system. Serving the report under the prefix already routed to this service removes the ambiguity by construction.

The pre-existing unguarded health path SHALL be left in place, because the container runtime probes it locally and never traverses the proxy.

#### Scenario: The dashboard receives this service's health, not a neighbour's

- **WHEN** the dashboard requests system health through the reverse proxy
- **THEN** the response carries this service's uptime, upstream-gateway status and free-disk figures, and not the neighbouring service's health document

#### Scenario: Health details are not readable without admin authentication

- **WHEN** system health is requested through the dashboard path without a valid admin session
- **THEN** the request is refused, so that free-disk and account-count figures are not disclosed

#### Scenario: The container probe keeps working

- **WHEN** the container runtime probes the original unguarded health path locally
- **THEN** it still receives the health report and the container liveness decision is unchanged

### Requirement: Process runtime is labelled as a restart interval

The elapsed-runtime figure SHALL be presented as time since the most recent process start, never as a bare availability figure.

The value resets to zero on every deployment. Presented as "uptime" it reads as an outage report on a perfectly healthy system that was simply released a few minutes ago. Because the service runs several worker processes and each holds its own start mark, consecutive reloads can return different values; the display SHALL note this rather than imply a single authoritative clock.

#### Scenario: A freshly deployed healthy system does not read as an incident

- **WHEN** the service has just been redeployed and every dependency is reachable
- **THEN** the health card names the figure as time since the last start, and the card's overall state is healthy

#### Scenario: Divergent worker clocks are disclosed

- **WHEN** the figure is displayed
- **THEN** the card notes that the value comes from whichever worker answered, so a shifted value between reloads is not read as a restart

### Requirement: The health card does not restate an account count under a shared name

The health card SHALL NOT display the account count carried in the health report.

The dashboard already shows two different figures under the same wording: the count of accounts that are not disabled, and the count of accounts that were actually used in the selected window. The health report's figure is a third instance of the first definition. Three placements carrying two definitions under one name is the label-does-not-match-value defect this project has removed twice before.

#### Scenario: Only one surface answers "how many users"

- **WHEN** the health card renders
- **THEN** it presents no account count, and the reader is left with the user-tab figures as the single source

### Requirement: Daily spend is compared against its own series

An unusual daily spend SHALL be reported by comparing the most recent complete interval against the mean of the series already retrieved for the chart, without issuing another query.

The comparison SHALL be withheld in two cases. When the series is shorter than the declared minimum, a multiple of the mean carries no information and an alarm raised on it will fire routinely until readers learn to ignore it. When the most recent interval is still open, its partial total is being compared against full-interval means, which compares two different quantities.

The declared minimum SHALL live in the same registry that carries the other minimum-sample declarations, so that thresholds remain declared in one place.

#### Scenario: A genuine spike is surfaced

- **WHEN** the most recent complete interval exceeds the series mean by more than the declared multiple, and the series meets the minimum length
- **THEN** the anomaly is reported together with both the interval figure and the series mean, so the reader can check the arithmetic

#### Scenario: A short series raises no alarm

- **WHEN** the series is shorter than the declared minimum
- **THEN** no anomaly is reported, and the reason given is the series length rather than the absence of a spike

#### Scenario: An interval still in progress is not judged

- **WHEN** the most recent interval has not yet closed
- **THEN** it is excluded from the comparison rather than reported as unusually low
