## Requirements

### Requirement: Complete backup package
The system SHALL create a timestamped backup package containing restorable backups of the `openwebui` database, `middleware` database, and `openwebui_data` volume.

#### Scenario: Successful complete backup
- **WHEN** all required components are backed up successfully
- **THEN** the system creates a completed package and manifest listing every required component

#### Scenario: Required component fails
- **WHEN** any required component cannot be backed up
- **THEN** the package is marked incomplete and is not reported as a valid restorable backup

### Requirement: Backup integrity manifest
Every completed backup package SHALL include component versions, timestamps, sizes, and checksums that can be verified before restore.

#### Scenario: Backup file is corrupted
- **WHEN** restore preflight calculates a checksum that differs from the manifest
- **THEN** restore stops before modifying production data

### Requirement: Scheduled backups and retention
The system SHALL support an idempotently installed daily backup schedule and configurable local retention.

#### Scenario: Daily scheduled run
- **WHEN** the configured daily schedule occurs
- **THEN** the backup workflow runs and records success or failure

#### Scenario: Retention cleanup
- **WHEN** a completed backup is older than the configured retention period
- **THEN** it is eligible for cleanup without deleting newer valid backups

### Requirement: Optional secondary destination
The system SHALL support copying completed backup packages to an optional configured secondary filesystem destination.

#### Scenario: Secondary destination unavailable
- **WHEN** the local backup succeeds but the secondary copy fails
- **THEN** the local backup remains valid and the secondary-copy failure is recorded

### Requirement: Controlled full restore
The system SHALL restore both databases and the Open WebUI data volume from a selected valid package only after explicit destructive-operation confirmation.

#### Scenario: Restore without confirmation
- **WHEN** an operator starts restore without the required confirmation switch
- **THEN** the system performs validation only and does not replace data

#### Scenario: Full restore succeeds
- **WHEN** an operator confirms restore of a valid complete package
- **THEN** the system restores all required components and restarts dependent services

### Requirement: Post-restore verification
The restore workflow MUST verify database connectivity, expected tables, middleware health, Open WebUI health, and selected data checks before reporting success.

#### Scenario: Service health check fails
- **WHEN** data restoration completes but a required health check fails
- **THEN** restore is reported as failed or incomplete with diagnostic details

### Requirement: Restore drill evidence
The system SHALL document and execute a non-production restore drill before scheduled production backups are considered operational.

#### Scenario: Restore drill completes
- **WHEN** a full backup is restored into the non-production target
- **THEN** the runbook records measured recovery time, restored components, verification results, and any failures
