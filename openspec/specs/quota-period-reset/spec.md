## Purpose
Define atomic quota period transitions before usage enforcement and accounting.

## Requirements

### Requirement: Persist quota period transition
The system SHALL atomically persist a user's new quota period anchor, reset period usage counters, and reset period alert eligibility when a weekly or monthly boundary is crossed.

#### Scenario: Monthly period changes
- **WHEN** a user's stored monthly period anchor is older than the current monthly anchor
- **THEN** the system updates that user's period anchor and resets only that user's period usage and period alert eligibility in one database transaction

#### Scenario: Period has not changed
- **WHEN** a user's stored period anchor matches the current period anchor
- **THEN** the system leaves the user's usage counters and alert eligibility unchanged

### Requirement: Reset before enforcement
The system MUST complete any required period reset before checking quota limits or adding new usage.

#### Scenario: First request in a new period
- **WHEN** a user sends the first request after a quota boundary
- **THEN** the request is evaluated against reset period usage rather than the previous period usage

### Requirement: Isolate user reset operations
Resetting one user's quota MUST NOT load, modify, or persist other users.

#### Scenario: Concurrent usage by another user
- **WHEN** user Alice is reset while user Bob's usage is incremented concurrently
- **THEN** Alice's reset does not overwrite Bob's usage update
