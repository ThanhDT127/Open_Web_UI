## Why

The repository has a script that dumps both PostgreSQL databases, but backups are not yet scheduled, do not include the Open WebUI data volume, and do not have a complete tested restore flow. The existing restore script restores only the `openwebui` database from a hard-coded SQL path.

A backup is only useful when it runs automatically, is verified, and can restore the complete system within an agreed recovery target.

## What Changes

- Create one production backup workflow covering the `openwebui` database, `middleware` database, Open WebUI data volume, and required configuration manifest.
- Add configurable retention and an optional secondary/offsite destination.
- Produce a backup manifest containing timestamp, included components, versions, checksums, and status.
- Add a matching restore workflow that can restore both databases and the Open WebUI data volume from a selected backup package.
- Remove hard-coded machine-specific restore paths.
- Add safe preflight checks, explicit confirmation for destructive restore operations, service stop/start handling, and post-restore verification.
- Add a scheduler installation/runbook for daily backups.
- Add a non-production restore drill and document RPO/RTO evidence.

## Capabilities

### New Capabilities

- `production-backup-recovery`: Scheduled, complete, verifiable backup and controlled full-system restore.

### Modified Capabilities

<!-- No existing capability requirement is modified. -->

## Impact

- Affected scripts: `scripts/backup_db.ps1`, `scripts/restore_openwebui_db.ps1`, and new scheduling/verification helpers.
- Affected persistence: PostgreSQL databases, `openwebui_data` volume, backup storage, and operational configuration metadata.
- Affected operations documentation: backup schedule, retention, restore runbook, restore drill, RPO, and RTO.
- Restore operations remain intentionally destructive and require explicit operator confirmation.
