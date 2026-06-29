#!/usr/bin/env powershell
# ==============================================================================
# Script: restore_openwebui_db.ps1
# Description: Controlled full restore of OpenWebUI from a versioned backup
#              package. Restores both PostgreSQL databases and the
#              openwebui_data volume. Requires explicit confirmation for any
#              destructive operation.
#
# Usage:
#   # Dry-run (preflight validation only, no data modification):
#   .\scripts\restore_openwebui_db.ps1 -Package ".\backups\backup_20260616_020000"
#
#   # Full restore (destructive):
#   .\scripts\restore_openwebui_db.ps1 -Package ".\backups\backup_20260616_020000" -Confirm
#
#   # Restore to a non-production target:
#   .\scripts\restore_openwebui_db.ps1 -Package ".\backups\backup_20260616_020000" -Confirm `
#       -TargetPostgres "test-postgres" -TargetApp "test-openwebui-app" -TargetMiddleware "test-middleware"
# ==============================================================================

param (
    [Parameter(Mandatory)]
    [string]$Package,

    [switch]$Confirm,

    [string]$TargetPostgres   = "openwebui-postgres",
    [string]$TargetApp        = "openwebui-app",
    [string]$TargetMiddleware = "openwebui-middleware",
    [string]$PgUser           = "openwebui_user"
)

$ErrorActionPreference = "Stop"

# Resolve paths
$PackageDir   = [System.IO.Path]::GetFullPath($Package)
$ManifestPath = Join-Path $PackageDir "manifest.json"
$ProjectRoot  = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$LogDir       = Join-Path $ProjectRoot "backups\logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile    = Join-Path $LogDir "restore_log.jsonl"
$RestoreTs  = Get-Date -Format "yyyyMMdd_HHmmss"
$ReportPath = Join-Path $PackageDir "restore_report_$RestoreTs.json"

# Helpers
function Write-Log {
    param([string]$Level, [string]$Msg)
    $entry = [ordered]@{
        ts      = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        level   = $Level
        package = (Split-Path $PackageDir -Leaf)
        message = $Msg
    }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogFile -Encoding UTF8
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN"  { "Yellow" }
        "OK"    { "Green" }
        default { "Cyan" }
    }
    Write-Host "[$Level] $Msg" -ForegroundColor $color
}

function Get-Sha256 {
    param([string]$FilePath)
    return (Get-FileHash -Path $FilePath -Algorithm SHA256).Hash.ToLower()
}

function Get-ContainerRunning {
    param([string]$Name)
    $state = docker inspect -f "{{.State.Running}}" $Name 2>$null
    return ($state -eq "true")
}

function Stop-IfRunning {
    param([string]$Name)
    if (Get-ContainerRunning $Name) {
        Write-Log "INFO" "Stopping $Name..."
        docker stop $Name | Out-Null
    }
}

function Start-IfNotRunning {
    param([string]$Name)
    if (-not (Get-ContainerRunning $Name)) {
        Write-Log "INFO" "Starting $Name..."
        docker start $Name | Out-Null
    }
}

# Restore report accumulator
$report = [ordered]@{
    package          = (Split-Path $PackageDir -Leaf)
    restore_ts       = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    dry_run          = (-not $Confirm.IsPresent)
    target_postgres  = $TargetPostgres
    preflight        = [ordered]@{ ok = $false; errors = @() }
    stages           = [ordered]@{}
    verification     = [ordered]@{}
    overall_status   = "pending"
    duration_s       = 0
}
$startTime = Get-Date

function Save-Report {
    $report.duration_s = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
    $report | ConvertTo-Json -Depth 10 | Set-Content -Path $ReportPath -Encoding UTF8
}

# ==============================================================================
# PHASE 1: PREFLIGHT VALIDATION
# ==============================================================================
Write-Host ""
Write-Host "=== OpenWebUI Restore - Preflight Check ===" -ForegroundColor Cyan
Write-Host ""
Write-Log "INFO" "Validating package: $PackageDir"

$errors = [System.Collections.Generic.List[string]]::new()

if (-not (Test-Path $PackageDir -PathType Container)) {
    $errors.Add("Package directory not found: $PackageDir")
}

if (-not (Test-Path $ManifestPath)) {
    $errors.Add("manifest.json not found in package")
}

if ($errors.Count -gt 0) {
    foreach ($e in $errors) { Write-Log "ERROR" $e }
    $report.preflight.errors = $errors.ToArray()
    $report.overall_status = "failed_preflight"
    Save-Report
    exit 1
}

$mf = Get-Content $ManifestPath | ConvertFrom-Json

if ($mf.complete -ne $true) {
    $errors.Add("Package is not marked complete - it may be from a failed backup run")
}

# Checksum verification for each component
$mf.components.PSObject.Properties | ForEach-Object {
    $cName = $_.Name
    $comp  = $_.Value
    if ($comp.status -eq "skipped") {
        Write-Log "WARN" "Component '$cName' was skipped during backup - will not be restored"
        return
    }
    if ($comp.status -ne "ok") {
        $errors.Add("Component '$cName' has status '$($comp.status)' in manifest")
        return
    }
    $filePath = Join-Path $PackageDir $comp.file
    if (-not (Test-Path $filePath)) {
        $errors.Add("Component '$cName' file not found: $($comp.file)")
        return
    }
    $actualHash = Get-Sha256 $filePath
    if ($actualHash -ne $comp.sha256) {
        $errors.Add("Component '$cName' checksum mismatch: expected $($comp.sha256) got $actualHash")
    } else {
        Write-Log "INFO" "Checksum OK: $cName ($($comp.file))"
    }
}

if (-not (Get-ContainerRunning $TargetPostgres)) {
    $errors.Add("Target postgres container '$TargetPostgres' is not running")
}

if ($errors.Count -gt 0) {
    foreach ($e in $errors) { Write-Log "ERROR" $e }
    $report.preflight.errors = $errors.ToArray()
    $report.overall_status = "failed_preflight"
    Save-Report
    Write-Host ""
    Write-Host "Preflight FAILED. No data was modified." -ForegroundColor Red
    exit 1
}

$report.preflight.ok = $true
$report.preflight.manifest_package = $mf.package
$report.preflight.manifest_completed_at = $mf.completed_at
$report.preflight.record_counts_from_backup = $mf.record_counts
Write-Log "OK" "Preflight passed."
Write-Host ""

# Dry-run stops here
if (-not $Confirm.IsPresent) {
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Host "  DRY RUN - Preflight OK. No data changed." -ForegroundColor Yellow
    Write-Host "  Re-run with -Confirm to execute restore." -ForegroundColor Yellow
    Write-Host "==========================================" -ForegroundColor Yellow
    $report.overall_status = "dry_run_ok"
    Save-Report
    Write-Host "  Report: $ReportPath" -ForegroundColor Cyan
    exit 0
}

# ==============================================================================
# PHASE 2: DESTRUCTIVE RESTORE
# ==============================================================================
Write-Host "WARNING: DESTRUCTIVE RESTORE CONFIRMED" -ForegroundColor Red
Write-Host "  Package : $(Split-Path $PackageDir -Leaf)" -ForegroundColor White
Write-Host "  Target  : $TargetPostgres" -ForegroundColor White
Write-Host "  Backed up: $($mf.completed_at)" -ForegroundColor White
Write-Host ""

# Stop application services
Write-Log "INFO" "Stopping application services..."
Stop-IfRunning $TargetApp
Stop-IfRunning $TargetMiddleware
$report.stages.stop_services = "ok"

# Restore middleware database
Write-Log "INFO" "Restoring 'middleware' database..."
$mwDump = Join-Path $PackageDir "middleware.dump"
try {
    docker cp $mwDump "${TargetPostgres}:/tmp/middleware.dump"
    docker exec $TargetPostgres psql -U $PgUser -d postgres --pset=pager=off -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='middleware' AND pid<>pg_backend_pid();" | Out-Null
    docker exec $TargetPostgres psql -U $PgUser -d postgres --pset=pager=off -c "DROP DATABASE IF EXISTS middleware;" | Out-Null
    docker exec $TargetPostgres psql -U $PgUser -d postgres --pset=pager=off -c "CREATE DATABASE middleware OWNER $PgUser;" | Out-Null
    docker exec $TargetPostgres pg_restore -U $PgUser -d middleware --no-owner "--role=$PgUser" /tmp/middleware.dump
    docker exec $TargetPostgres rm /tmp/middleware.dump
    $report.stages.restore_middleware_db = "ok"
    Write-Log "OK" "middleware DB restored."
} catch {
    Write-Log "ERROR" "middleware DB restore failed: $_"
    $report.stages.restore_middleware_db = "failed: $_"
    $report.overall_status = "failed"
    Save-Report
    Write-Host "Restore failed at middleware DB. Starting services back up..." -ForegroundColor Red
    Start-IfNotRunning $TargetMiddleware
    Start-IfNotRunning $TargetApp
    exit 1
}

# Restore openwebui database
Write-Log "INFO" "Restoring 'openwebui' database..."
$owDump = Join-Path $PackageDir "openwebui.dump"
try {
    docker cp $owDump "${TargetPostgres}:/tmp/openwebui.dump"
    docker exec $TargetPostgres psql -U $PgUser -d postgres --pset=pager=off -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='openwebui' AND pid<>pg_backend_pid();" | Out-Null
    docker exec $TargetPostgres psql -U $PgUser -d postgres --pset=pager=off -c "DROP DATABASE IF EXISTS openwebui;" | Out-Null
    docker exec $TargetPostgres psql -U $PgUser -d postgres --pset=pager=off -c "CREATE DATABASE openwebui OWNER $PgUser;" | Out-Null
    docker exec $TargetPostgres psql -U $PgUser -d openwebui --pset=pager=off -c "CREATE EXTENSION IF NOT EXISTS vector;" | Out-Null
    docker exec $TargetPostgres pg_restore -U $PgUser -d openwebui --no-owner "--role=$PgUser" /tmp/openwebui.dump
    docker exec $TargetPostgres rm /tmp/openwebui.dump
    $report.stages.restore_openwebui_db = "ok"
    Write-Log "OK" "openwebui DB restored."
} catch {
    Write-Log "ERROR" "openwebui DB restore failed: $_"
    $report.stages.restore_openwebui_db = "failed: $_"
    $report.overall_status = "failed"
    Save-Report
    Write-Host "Restore failed at openwebui DB. Starting services back up..." -ForegroundColor Red
    Start-IfNotRunning $TargetMiddleware
    Start-IfNotRunning $TargetApp
    exit 1
}

# Restore openwebui_data volume
$volArchive = Join-Path $PackageDir "openwebui_data.tar.gz"
$volComp = $mf.components.data_volume
if ($volComp.status -eq "skipped") {
    Write-Log "WARN" "openwebui_data was skipped in backup - volume not restored."
    $report.stages.restore_data_volume = "skipped"
} elseif (-not (Test-Path $volArchive)) {
    Write-Log "WARN" "openwebui_data archive not found - volume not restored."
    $report.stages.restore_data_volume = "skipped_missing_file"
} else {
    Write-Log "INFO" "Restoring openwebui_data volume..."
    try {
        docker run --rm -v "openwebui_clone_openwebui_data:/data" -v "${PackageDir}:/backup:ro" alpine sh -c "rm -rf /data/* /data/..?* /data/.[!.]* 2>/dev/null; tar xzf /backup/openwebui_data.tar.gz -C /data"
        $report.stages.restore_data_volume = "ok"
        Write-Log "OK" "openwebui_data volume restored."
    } catch {
        Write-Log "ERROR" "Volume restore failed: $_"
        $report.stages.restore_data_volume = "failed: $_"
        $report.overall_status = "failed"
        Save-Report
        Write-Host "Volume restore failed. Starting services back up..." -ForegroundColor Red
        Start-IfNotRunning $TargetMiddleware
        Start-IfNotRunning $TargetApp
        exit 1
    }
}

# Restart services
Write-Log "INFO" "Restarting application services..."
Start-IfNotRunning $TargetMiddleware
Start-IfNotRunning $TargetApp
Start-Sleep -Seconds 10
$report.stages.restart_services = "ok"

# ==============================================================================
# PHASE 3: POST-RESTORE VERIFICATION
# ==============================================================================
Write-Log "INFO" "Running post-restore verification..."
$verif = [ordered]@{}

# 4.1 DB connectivity and expected tables
try {
    $tables = docker exec $TargetPostgres psql -U $PgUser -d middleware -tAc "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
    $tableList = $tables -split "`n" | Where-Object { $_ -ne "" }
    $requiredTables = @("mw_users", "mw_audit_log", "mw_prices", "mw_config")
    $missingTables = $requiredTables | Where-Object { $tableList -notcontains $_ }
    if ($missingTables.Count -eq 0) {
        $verif.middleware_tables = "ok"
        Write-Log "OK" "All required middleware tables present."
    } else {
        $verif.middleware_tables = "missing: " + ($missingTables -join ", ")
        Write-Log "WARN" ("Missing tables in middleware: " + ($missingTables -join ", "))
    }
} catch {
    $verif.middleware_tables = "error: $_"
    Write-Log "WARN" "Could not verify middleware tables: $_"
}

try {
    $owTables = docker exec $TargetPostgres psql -U $PgUser -d openwebui -tAc "SELECT tablename FROM pg_tables WHERE schemaname='public' LIMIT 5;"
    $verif.openwebui_db_accessible = if ($owTables) { "ok" } else { "no_tables_found" }
    Write-Log "OK" "openwebui DB accessible."
} catch {
    $verif.openwebui_db_accessible = "error: $_"
    Write-Log "WARN" "Could not verify openwebui DB: $_"
}

# 4.2 Record counts vs backup manifest
try {
    $restoredUsers = docker exec $TargetPostgres psql -U $PgUser -d middleware -tAc "SELECT COUNT(*) FROM mw_users;"
    $restoredAudit = docker exec $TargetPostgres psql -U $PgUser -d middleware -tAc "SELECT COUNT(*) FROM mw_audit_log;"
    $backupUsers   = $mf.record_counts.mw_users
    $backupAudit   = $mf.record_counts.mw_audit_log
    $rUsers = [int]($restoredUsers.Trim())
    $rAudit = [int]($restoredAudit.Trim())
    $verif.record_counts = [ordered]@{
        mw_users     = [ordered]@{ backup = $backupUsers; restored = $rUsers; match = ($rUsers -eq $backupUsers) }
        mw_audit_log = [ordered]@{ backup = $backupAudit; restored = $rAudit; match = ($rAudit -eq $backupAudit) }
    }
    if ($verif.record_counts.mw_users.match -and $verif.record_counts.mw_audit_log.match) {
        Write-Log "OK" "Record counts match backup manifest."
    } else {
        Write-Log "WARN" "Record count mismatch (may be expected for non-production drill)."
    }
} catch {
    $verif.record_counts = "error: $_"
    Write-Log "WARN" "Could not verify record counts: $_"
}

# 4.3 Middleware health
try {
    Start-Sleep -Seconds 5
    $mwHealth = (Invoke-WebRequest -Uri "http://localhost:5000/health" -UseBasicParsing -TimeoutSec 10).StatusCode
    $verif.middleware_health = if ($mwHealth -eq 200) { "ok" } else { "http_$mwHealth" }
    Write-Log "OK" "Middleware health: HTTP $mwHealth"
} catch {
    $verif.middleware_health = "unreachable: $_"
    Write-Log "WARN" "Middleware health check failed: $_"
}

# 4.4 Assemble verification
$report.verification  = $verif
$criticalFailed = (
    $verif.middleware_tables -ne "ok" -or
    $verif.openwebui_db_accessible -ne "ok"
)
$report.overall_status = if ($criticalFailed) { "restored_with_warnings" } else { "ok" }
Save-Report

# Human-readable summary
Write-Host ""
$headerColor = if ($criticalFailed) { "Yellow" } else { "Green" }
Write-Host "=== Restore Verification Report ===" -ForegroundColor $headerColor
Write-Host "  Package  : $(Split-Path $PackageDir -Leaf)" -ForegroundColor White
Write-Host "  Status   : $($report.overall_status)" -ForegroundColor $headerColor
Write-Host "  Duration : $($report.duration_s)s" -ForegroundColor White
Write-Host "  Report   : $ReportPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Stages:" -ForegroundColor Cyan
foreach ($stageEntry in $report.stages.GetEnumerator()) {
    $icon = if ($stageEntry.Value -match "^ok$|^skipped") { "[OK]" } else { "[FAIL]" }
    Write-Host "    $icon $($stageEntry.Key): $($stageEntry.Value)" -ForegroundColor White
}
Write-Host ""
Write-Host "  Verification:" -ForegroundColor Cyan
Write-Host "    DB tables (middleware): $($verif.middleware_tables)" -ForegroundColor White
Write-Host "    DB openwebui access   : $($verif.openwebui_db_accessible)" -ForegroundColor White
Write-Host "    Middleware health     : $($verif.middleware_health)" -ForegroundColor White

Write-Host ""
if ($criticalFailed) {
    Write-Host "WARNING: Restore completed with issues. Review the report." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "Restore successful." -ForegroundColor Green
    exit 0
}
