# Backup & Restore Runbook — OpenWebUI Production

## Overview

| Item | Value |
|---|---|
| Backup script | `scripts/backup_db.ps1` |
| Restore script | `scripts/restore_openwebui_db.ps1` |
| Scheduler installer | `scripts/install_backup_schedule.ps1` |
| Backup location | `<project>/backups/backup_<timestamp>/` |
| Log file | `<project>/backups/logs/backup_log.jsonl` |
| Default schedule | Daily 02:00 AM (local time) |
| Default retention | 7 days (complete packages only) |
| Covered components | `openwebui` DB, `middleware` DB, `openwebui_data` volume |

**RPO (Recovery Point Objective):** ≤ 24 hours (daily schedule).  
**RTO (Recovery Time Objective):** ≤ 30 minutes (measured in restore drill — see §6).

---

## 1. Manual Backup

```powershell
# From project root:
.\scripts\backup_db.ps1
```

With options:
```powershell
# Custom retention (14 days) and secondary destination:
.\scripts\backup_db.ps1 -RetentionDays 14 -SecondaryDest "\\nas\openwebui-backups"

# Skip volume backup (faster, DBs only):
.\scripts\backup_db.ps1 -SkipVolumeBackup
```

After a successful backup, verify the package:
```powershell
ls backups\backup_<timestamp>\
# Should contain: openwebui.dump  middleware.dump  openwebui_data.tar.gz  manifest.json
cat backups\backup_<timestamp>\manifest.json | ConvertFrom-Json | Select complete, completed_at, components
```

> [!IMPORTANT]
> A package is only valid if `manifest.json` has `"complete": true`.  
> Incomplete packages are kept for diagnostics but **cannot be used for restore**.

---

## 2. Restore from Backup

### Step 1 — Dry-run (validation only)

Always run a dry-run first. This validates the package integrity without touching any data:

```powershell
.\scripts\restore_openwebui_db.ps1 -Package ".\backups\backup_20260616_020000"
```

The dry-run will:
- Check that `manifest.json` exists and has `"complete": true`
- Verify SHA-256 checksums for every component file
- Confirm the target Postgres container is reachable
- **Not** modify any database or volume

### Step 2 — Full restore (destructive)

> [!CAUTION]
> This stops OpenWebUI and replaces databases and volume data.  
> All changes made after the backup timestamp will be lost.

```powershell
.\scripts\restore_openwebui_db.ps1 `
    -Package ".\backups\backup_20260616_020000" `
    -Confirm
```

The restore script will:
1. Stop `openwebui-app` and `openwebui-middleware`
2. Restore `middleware` database via `pg_restore`
3. Restore `openwebui` database via `pg_restore`
4. Restore `openwebui_data` volume
5. Restart services
6. Run post-restore verification (tables, record counts, health)
7. Write a JSON + human-readable report in the package folder

Check the report:
```powershell
cat backups\backup_<timestamp>\restore_report_<timestamp>.json | ConvertFrom-Json
```

### Restore to non-production target

```powershell
.\scripts\restore_openwebui_db.ps1 `
    -Package ".\backups\backup_20260616_020000" `
    -Confirm `
    -TargetPostgres "test-postgres" `
    -TargetApp "test-openwebui-app" `
    -TargetMiddleware "test-middleware"
```

---

## 3. Scheduled Daily Backup

### Install the task

```powershell
# Run as Administrator:
.\scripts\install_backup_schedule.ps1

# With custom time and retention:
.\scripts\install_backup_schedule.ps1 -TriggerTime "03:00" -BackupArgs "-RetentionDays 14"

# With secondary destination:
.\scripts\install_backup_schedule.ps1 -BackupArgs "-SecondaryDest '\\nas\openwebui-backups'"
```

### Manage the task

```powershell
# View status and last run result:
.\scripts\install_backup_schedule.ps1 -Status

# Run immediately:
.\scripts\install_backup_schedule.ps1 -RunNow

# Disable without removing:
Disable-ScheduledTask -TaskName "OpenWebUI-DailyBackup"

# Re-enable:
Enable-ScheduledTask -TaskName "OpenWebUI-DailyBackup"

# Remove:
.\scripts\install_backup_schedule.ps1 -Uninstall
```

### Backup failure signals

- **Task Scheduler Last Run Result ≠ 0** → backup failed. Check `backups\logs\backup_log.jsonl`.
- **Package manifest has `"complete": false`** → backup was interrupted mid-run.
- **No new `backup_*` folder today** → task did not run. Check Task Scheduler history.

View the log:
```powershell
Get-Content backups\logs\backup_log.jsonl | ForEach-Object { $_ | ConvertFrom-Json } | Format-Table ts, level, message
```

---

## 4. Retention and Secondary Destination

### Retention

- Default: 7 days.
- Only **complete** packages are deleted during retention cleanup.
- Incomplete (failed) packages are preserved for diagnostics.
- Change retention per-run: `-RetentionDays 14`
- Change retention in the scheduled task: re-run `install_backup_schedule.ps1 -BackupArgs "-RetentionDays 14"`

### Secondary destination

Configure a secondary copy target (NAS share, external drive, another server):

```powershell
.\scripts\backup_db.ps1 -SecondaryDest "\\fileserver\openwebui-backups"
```

- The secondary copy is optional. A failure to copy does **not** invalidate the local backup.
- Secondary copy failure is logged and recorded in `manifest.json` as `secondary_copy_error`.

### Filesystem permissions

| Path | Required access |
|---|---|
| `<project>\backups\` | Write — task user |
| `<project>\backups\logs\` | Write — task user |
| Secondary destination | Write — task user or service account |

Verify write access before enabling scheduled backups:
```powershell
# Test write to backup dir:
[System.IO.File]::WriteAllText(".\backups\test_write", "ok"); Remove-Item ".\backups\test_write"
```

---

## 5. What Is (and Is Not) Included in Backups

### Included
- PostgreSQL database `openwebui` (all chat history, users, knowledge bases)
- PostgreSQL database `middleware` (users, quotas, audit logs, pricing)
- `openwebui_data` Docker volume (uploaded files, model data, configuration)
- Container image versions and postgres version (recorded in manifest)

### Excluded (intentional)
- `.env` file — contains API keys and secrets
- `nginx/ssl/` — SSL private keys
- `vertex.json` — GCP service account key
- `litellm_logs` volume — operational logs only, not required for recovery

---

## 6. Restore Drill Log

### Drill 1 — 2026-06-16

| Item | Result |
|---|---|
| Backup package | `backup_20260616_092924` |
| Backup size | openwebui_db: 16.5 MB · middleware_db: 0.27 MB · data_volume: 238.15 MB |
| Backup duration | ~30 seconds |
| Dry-run validation | Pass — checksums verified, manifest `complete: true` |
| Restore target | Production (`openwebui-postgres`, same host) |
| Restore duration | **47.8 seconds** |
| Middleware tables | All required tables present |
| openwebui DB accessible | Yes |
| mw_users count match | Yes (4/4) |
| mw_audit_log count match | Yes (50/50) |
| Middleware health | HTTP 200 |
| Discovered issues | None — restore fully automatic |

**Total measured RTO:** ~80 seconds (backup verify + restore + verification)

> [!NOTE]
> Production daily schedule can now be enabled.
> Run: `.\scripts\install_backup_schedule.ps1`

---

## 7. Quick Reference

```powershell
# Backup now
.\scripts\backup_db.ps1

# Validate a package (dry-run)
.\scripts\restore_openwebui_db.ps1 -Package ".\backups\backup_<ts>"

# Restore (destructive)
.\scripts\restore_openwebui_db.ps1 -Package ".\backups\backup_<ts>" -Confirm

# Install daily schedule
.\scripts\install_backup_schedule.ps1

# Check schedule status
.\scripts\install_backup_schedule.ps1 -Status

# View backup log
Get-Content backups\logs\backup_log.jsonl | ForEach-Object { $_ | ConvertFrom-Json } | ft ts, level, message
```
