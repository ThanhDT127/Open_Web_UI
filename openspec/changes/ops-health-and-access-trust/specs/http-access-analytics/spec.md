## ADDED Requirements

### Requirement: A broken data source is reported, not silently substituted

When the primary store for access statistics cannot be read, the summary SHALL fail loudly rather than fall through to a secondary source.

The two sources cover different retention and different rows, so a silent substitution makes this tab disagree with every other tab on the same window while presenting both as ordinary figures. A reader comparing tabs concludes the numbers are unreliable, not that one source is down. Where a secondary source is genuinely wanted, it SHALL be selected deliberately rather than reached by swallowing an exception.

The display SHALL clear the previous figures when it reports the failure. An error notice sitting above a populated table still reads as though those figures belong to the selected window.

#### Scenario: A store outage is visible as an outage

- **WHEN** the primary store cannot be read for the selected window
- **THEN** the request fails, the tab shows an error notice, and every figure and table on it is cleared

#### Scenario: Figures from a previous window do not survive an error

- **WHEN** a window loads successfully and a subsequent window fails
- **THEN** the earlier window's figures are removed rather than left beneath the error notice

### Requirement: Access statistics use the shared time-range resolver

The access summary SHALL resolve its time range through the same resolver every other analytics endpoint uses, preserving its existing default window by passing that default explicitly.

A private copy of the resolver drifts from the shared one, and the drift is silent: the same malformed parameter produces a refusal on one endpoint and an unrequested window on another. This is the last remaining copy.

#### Scenario: A malformed range is refused consistently

- **WHEN** an unparseable start or end value is supplied to the access summary
- **THEN** it is refused with the same failure the other analytics endpoints produce for the same input

#### Scenario: The historical default window is unchanged

- **WHEN** no explicit range is supplied
- **THEN** the summary covers the same default window it covered before the resolver was shared

### Requirement: Error counts are split by the response they demand

The summary SHALL report failures, refusals and throttling as separate figures rather than as one combined error rate.

A server fault means a person must be called; a refusal means an access decision should be reviewed; throttling means a limit may need raising. Combining them yields a number that supports none of those actions. The groups SHALL NOT overlap, and the groups together with the remaining client errors SHALL account for exactly the rows the combined figure previously covered, so that no row is counted twice and none is dropped.

The service's own liveness probe SHALL be excluded from the failure group and reported separately. The probe is the service examining itself, not a user encountering an error, and its volume otherwise dominates the group to the point of concealing real faults.

#### Scenario: The split accounts for every error row

- **WHEN** a window is summarised
- **THEN** failures, refusals, throttling, the remaining client errors and the liveness-probe failures sum to the total count of error responses in that window

#### Scenario: Throttling is not presented as a refusal

- **WHEN** requests were rejected for exceeding a rate limit
- **THEN** they are reported as throttling and are absent from the refusal figure

#### Scenario: Self-probe failures do not conceal real faults

- **WHEN** the liveness probe has failed many times in the window
- **THEN** those responses are reported under their own figure and are excluded from the failure group

### Requirement: Per-path error columns report measurements

Each row of the busiest-paths breakdown SHALL carry that path's own error count and error rate, computed from the same rows that produced its request count.

Rendering a column the payload does not contain yields a constant, and a constant presented in a column beside real measurements is read as a measurement. The per-path error counts SHALL sum to the window's total error count.

#### Scenario: Per-path errors reconcile with the total

- **WHEN** the breakdown is rendered for a window containing error responses
- **THEN** the per-path error counts sum to the window's total error count, and at least one row is non-zero

### Requirement: Latency percentiles disclose their sample base

A latency percentile of zero SHALL be reported as zero rather than as absent, and the summary SHALL carry the number of responses that contributed a duration.

Treating the value as absent when it is falsy erases a genuine measurement. Separately, responses without a recorded duration — and responses recorded as zero — are excluded from the percentile, so its sample base is smaller than the request count; a percentile whose coverage is partial SHALL disclose that coverage rather than imply it was computed over every request.

#### Scenario: A genuine zero percentile is reported

- **WHEN** every contributing response in the window recorded a duration of zero
- **THEN** the percentile is reported as zero rather than as absent

#### Scenario: Partial coverage is disclosed

- **WHEN** fewer responses carried a duration than the window's request count
- **THEN** the sample count accompanies the percentile so the reader can judge its weight

### Requirement: Failed dashboard sign-ins are named for the door they guard

The count of rejected sign-ins SHALL be labelled as attempts against the dashboard specifically.

End-user sign-ins are routed by the reverse proxy to the application service and never traverse this service, so they cannot appear in this figure. A label that omits the distinction invites the reader to conclude that end-user credentials are being probed, from data that could not carry that signal.

#### Scenario: The figure names its scope

- **WHEN** the rejected sign-in count is displayed
- **THEN** its label identifies dashboard sign-ins, not sign-ins generally

### Requirement: The recorded caller address is the caller's, not the proxy's

The request log SHALL record the originating caller's address when the request arrives through the trusted reverse proxy.

Without this, every request records the proxy's own address and the field distinguishes nothing: the recorded values enumerate the container topology rather than the callers. The set of addresses permitted to assert a forwarded caller SHALL be declared explicitly; permitting any origin to assert it turns the record into a field the caller controls.

#### Scenario: A proxied request records the originating address

- **WHEN** a request reaches the service through the trusted reverse proxy
- **THEN** the log records the originating caller's address rather than the proxy's

#### Scenario: An untrusted origin cannot assert an address

- **WHEN** a request from outside the declared trusted range asserts a forwarded caller address
- **THEN** that assertion is disregarded and the observed connection address is recorded
