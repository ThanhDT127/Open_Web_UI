## Purpose
Define consistent, precise, and deduplicated quota alert behavior.

## Requirements

### Requirement: Evaluate alerts from committed quota state
The system SHALL evaluate quota alert thresholds using the latest committed quota usage and limit for exactly one user.

#### Scenario: Limit changed before alert evaluation
- **WHEN** an administrator commits a new quota limit before alert evaluation starts
- **THEN** the alert evaluation uses the new committed limit

### Requirement: Preserve alert-time quota snapshot
Each quota notification SHALL store the exact usage, limit, percentage, threshold, and period anchor used to create it.

#### Scenario: Limit changes after alert delivery
- **WHEN** a quota alert is delivered and the administrator later changes the user's limit
- **THEN** the historical notification retains the original alert-time values

### Requirement: Prevent duplicate threshold alerts
The system MUST create at most one alert for the same user, quota period, threshold, and alert type.

#### Scenario: Concurrent requests cross a threshold
- **WHEN** multiple requests complete concurrently and cross the same threshold
- **THEN** only one notification and one corresponding email are created for that threshold

### Requirement: Display precise small currency values
The system SHALL format quota alert currency values with enough precision to distinguish values below one dollar and SHALL NOT display a negative remaining amount.

#### Scenario: Limit is below one cent
- **WHEN** the alert snapshot limit is `0.008 USD`
- **THEN** the alert message displays a value that distinguishes `0.008` from `0.01` and displays remaining usage as no less than zero

### Requirement: Dashboard and alerts share quota source
The dashboard quota view and alert evaluation SHALL read quota limits and usage from the same committed database record.

#### Scenario: Administrator saves a ten dollar limit
- **WHEN** the dashboard confirms that a user's saved limit is `10 USD`
- **THEN** subsequent dashboard reads and alert evaluations both use `10 USD`
