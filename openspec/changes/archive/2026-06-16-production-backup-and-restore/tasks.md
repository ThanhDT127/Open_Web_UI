## 1. Define Backup Package and Configuration

- [x] 1.1 Define parameters for local backup path, retention days, optional secondary destination, and maintenance behavior
- [x] 1.2 Define the versioned manifest schema with component versions, timestamps, sizes, checksums, and status
- [x] 1.3 Document which configuration metadata is included and which secrets are intentionally excluded

## 2. Implement Complete Backup

- [x] 2.1 Update the backup workflow to create custom-format dumps for both `openwebui` and `middleware`
- [x] 2.2 Add a consistent archive of the `openwebui_data` volume with controlled Open WebUI pause/stop handling
- [x] 2.3 Generate checksums and a completed manifest only after all required components succeed
- [x] 2.4 Preserve failed or incomplete-run diagnostics without presenting incomplete packages as valid backups
- [x] 2.5 Add configurable retention cleanup that preserves newer valid packages
- [x] 2.6 Add optional copy of completed packages to the configured secondary destination

## 3. Implement Controlled Full Restore

- [x] 3.1 Replace the hard-coded restore path with a required selected backup package parameter
- [x] 3.2 Add manifest and checksum validation before any destructive operation
- [x] 3.3 Require an explicit destructive restore confirmation switch
- [x] 3.4 Stop dependent services and restore both databases using `pg_restore`
- [x] 3.5 Restore the `openwebui_data` volume and restart dependent services safely
- [x] 3.6 Add failure handling that reports the failed stage and preserves diagnostic logs

## 4. Add Verification

- [x] 4.1 Verify restored PostgreSQL connectivity and expected tables in both databases
- [x] 4.2 Verify selected record counts against values recorded in the backup manifest
- [x] 4.3 Verify middleware health and Open WebUI health after restore
- [x] 4.4 Produce a machine-readable and human-readable restore verification report

## 5. Schedule and Operate

- [x] 5.1 Add an idempotent PowerShell script for installing or updating a Windows Task Scheduler daily backup task
- [x] 5.2 Add commands for manually running, disabling, and inspecting the scheduled task
- [x] 5.3 Add backup failure logging and a clear operator-visible failure signal
- [x] 5.4 Document filesystem permissions for local and secondary backup destinations

## 6. Restore Drill and Documentation

- [x] 6.1 Run a complete manual backup and verify its manifest and checksums
- [x] 6.2 Restore the package into a non-production target
- [x] 6.3 Record measured recovery time, restored components, verification results, and discovered issues
- [x] 6.4 Update the operations runbook with backup, restore, retention, secondary copy, RPO, and RTO procedures
- [x] 6.5 Enable the production daily schedule only after the restore drill passes
