## Context

The current backup script dumps both PostgreSQL databases into a zip file and retains backups for seven days. It does not archive `openwebui_data`, generate checksums or a manifest, install a schedule, copy offsite, or verify restore. The current restore script restores only the Open WebUI database from a machine-specific default path.

## Goals / Non-Goals

**Goals:**

- Back up all required production data automatically.
- Restore a selected complete backup safely.
- Verify backup integrity and exercise restore in non-production.
- Make retention and secondary destination configurable.

**Non-Goals:**

- Provide zero-downtime database replication.
- Replace PostgreSQL-native backup tools.
- Select a mandatory NAS or cloud provider.

## Decisions

### 1. Use a versioned backup package with manifest

Each backup run will create one timestamped package containing both database dumps, the Open WebUI data volume archive, and a JSON manifest with component versions, checksums, sizes, and completion status.

Incomplete packages will not be treated as restorable backups.

### 2. Use PostgreSQL custom-format dumps

Database backups will use `pg_dump --format=custom` to support reliable `pg_restore`, explicit error handling, and future parallel restore.

### 3. Make local retention and secondary copy configurable

Local backup directory and retention days will be parameters. A secondary destination will be optional and configured as a filesystem path so it can target NAS or another mounted location without provider-specific code.

### 4. Require explicit destructive restore confirmation

Restore will validate package integrity and require an explicit command switch before stopping services or replacing databases/data volume. Machine-specific hard-coded paths will be removed.

### 5. Verify after restore

Restore completion requires database connectivity, middleware health, Open WebUI health, expected table presence, and selected record-count checks. A restore drill will run against a non-production target.

### 6. Use Windows Task Scheduler for the initial scheduler

The current host environment is Windows and the operational scripts are PowerShell. The change will provide an idempotent Task Scheduler installation script and a documented manual alternative.

## Risks / Trade-offs

- [Volume archive changes while backup runs] -> Stop or pause Open WebUI during the volume archive step and document the short maintenance impact.
- [Backup package contains sensitive data] -> Restrict filesystem permissions and do not include plaintext secrets unless explicitly requested.
- [Secondary destination unavailable] -> Keep the verified local backup and record secondary-copy failure in the manifest/log.
- [Restore destroys current state] -> Require preflight validation, explicit confirmation, and a pre-restore safety backup option.

## Migration Plan

1. Introduce the versioned backup package and manifest while keeping the current script available.
2. Run and verify a complete manual backup.
3. Implement full restore and execute a non-production restore drill.
4. Install the daily schedule only after the drill passes.
5. Configure retention and optional secondary destination.
6. Roll back by disabling the scheduled task; existing backup packages remain readable.

## Open Questions

- Final secondary backup destination and retention period.
- Acceptable maintenance window for consistent `openwebui_data` volume backup.
