#!/usr/bin/env powershell
# ==============================================================================
# Script: backup_db.ps1
# Description: Complete production backup for OpenWebUI.
#              Dumps both PostgreSQL databases and archives the openwebui_data
#              volume. Produces a versioned package with a JSON manifest,
#              SHA-256 checksums, configurable retention, and optional copy
#              to a secondary destination.
#
# Usage:
#   .\scripts\backup_db.ps1
#   .\scripts\backup_db.ps1 -BackupRoot "D:\backups" -RetentionDays 14
#   .\scripts\backup_db.ps1 -SecondaryDest "\\nas\openwebui-backups"
#   .\scripts\backup_db.ps1 -SkipVolumeBackup
#
# Manifest schema (manifest.json inside each package folder):
#   {
#     "version": "2",
#     "package": "<timestamp>",
#     "started_at": "<ISO8601>",
#     "completed_at": "<ISO8601>",
#     "complete": true|false,
#     "postgres_version": "<string>",
#     "components": {
#       "openwebui_db":  { "file": "openwebui.dump",  "size_bytes": N, "sha256": "<hash>", "status": "ok"|"failed" },
#       "middleware_db": { "file": "middleware.dump",  "size_bytes": N, "sha256": "<hash>", "status": "ok"|"failed" },
#       "data_volume":   { "file": "openwebui_data.tar.gz", "size_bytes": N, "sha256": "<hash>", "status": "ok"|"skipped"|"failed" }
#     },
#     "record_counts": { "mw_users": N, "mw_audit_log": N },
#     "error": "<message>"
#   }
#
# Excluded from backup: .env secrets, SSL private keys, API keys.
# ==============================================================================

param (
    [string]$BackupRoot     = "",
    [int]   $RetentionDays  = 7,
    [string]$SecondaryDest  = "",
    [switch]$SkipVolumeBackup
)

$ErrorActionPreference = "Stop"

# Resolve paths
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if (-not $BackupRoot) {
    $BackupRoot = Join-Path $ProjectRoot "backups"
}
$LogDir = Join-Path $BackupRoot "logs"

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$Timestamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$PackageName = "backup_$Timestamp"
$PackageDir  = Join-Path $BackupRoot $PackageName
$LogFile     = Join-Path $LogDir "backup_log.jsonl"
$StartedAt   = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

New-Item -ItemType Directory -Path $PackageDir -Force | Out-Null

# Helper: structured JSON log
function Write-Log {
    param([string]$Level, [string]$Message)
    $entry = [ordered]@{
        ts      = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        level   = $Level
        package = $PackageName
        message = $Message
    }
    ($entry | ConvertTo-Json -Compress) | Add-Content -Path $LogFile -Encoding UTF8
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN"  { "Yellow" }
        "OK"    { "Green" }
        default { "Cyan" }
    }
    Write-Host "[$Level] $Message" -ForegroundColor $color
}

# Helper: SHA-256 of a file
function Get-Sha256 {
    param([string]$FilePath)
    return (Get-FileHash -Path $FilePath -Algorithm SHA256).Hash.ToLower()
}

# Helper: get image tag of a container
function Get-ContainerImage {
    param([string]$ContainerName)
    try {
        $img = docker inspect --format "{{.Config.Image}}" $ContainerName 2>$null
        if ($img) { return $img.Trim() } else { return "unknown" }
    } catch {
        return "unknown"
    }
}

# Helper: check if container is running
function Get-ContainerRunning {
    param([string]$ContainerName)
    $state = docker inspect -f "{{.State.Running}}" $ContainerName 2>$null
    return ($state -eq "true")
}

# Initialise manifest as a hashtable
$manifest = [ordered]@{
    version          = "2"
    package          = $PackageName
    started_at       = $StartedAt
    completed_at     = $null
    complete         = $false
    postgres_version = "unknown"
    middleware_image = Get-ContainerImage "openwebui-middleware"
    openwebui_image  = Get-ContainerImage "openwebui-app"
    components       = [ordered]@{
        openwebui_db  = [ordered]@{ file = "openwebui.dump";        size_bytes = 0; sha256 = ""; status = "pending" }
        middleware_db = [ordered]@{ file = "middleware.dump";        size_bytes = 0; sha256 = ""; status = "pending" }
        data_volume   = [ordered]@{ file = "openwebui_data.tar.gz"; size_bytes = 0; sha256 = ""; status = "pending" }
    }
    record_counts    = [ordered]@{}
    error            = $null
}

function Save-Manifest {
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -Path (Join-Path $PackageDir "manifest.json") -Encoding UTF8
}

Save-Manifest

# Preflight: postgres container must be running
Write-Log "INFO" "Preflight: checking openwebui-postgres container..."
if (-not (Get-ContainerRunning "openwebui-postgres")) {
    Write-Log "ERROR" "Container openwebui-postgres is not running. Backup aborted."
    $manifest.error = "postgres container not running"
    Save-Manifest
    exit 1
}

# Collect postgres version
try {
    $pgVer = docker exec openwebui-postgres psql -U openwebui_user -d postgres -tAc "SELECT version();"
    $manifest.postgres_version = $pgVer.Trim()
} catch {
    Write-Log "WARN" "Could not retrieve postgres version: $_"
}

# Step 1: Dump openwebui database
Write-Log "INFO" "Dumping database 'openwebui' (custom format)..."
$owDump = Join-Path $PackageDir "openwebui.dump"
try {
    docker exec openwebui-postgres pg_dump -U openwebui_user -d openwebui --format=custom -f /tmp/openwebui.dump
    docker cp "openwebui-postgres:/tmp/openwebui.dump" $owDump
    docker exec openwebui-postgres rm /tmp/openwebui.dump

    $manifest.components.openwebui_db.size_bytes = (Get-Item $owDump).Length
    $manifest.components.openwebui_db.sha256     = Get-Sha256 $owDump
    $manifest.components.openwebui_db.status     = "ok"
    Write-Log "INFO" ("openwebui DB dump OK - " + [math]::Round((Get-Item $owDump).Length / 1MB, 2) + " MB")
} catch {
    Write-Log "ERROR" "openwebui DB dump failed: $_"
    $manifest.components.openwebui_db.status = "failed"
    $manifest.error = "openwebui_db dump failed: $_"
    Save-Manifest
    exit 1
}
Save-Manifest

# Step 2: Dump middleware database
Write-Log "INFO" "Dumping database 'middleware' (custom format)..."
$mwDump = Join-Path $PackageDir "middleware.dump"
try {
    docker exec openwebui-postgres pg_dump -U openwebui_user -d middleware --format=custom -f /tmp/middleware.dump
    docker cp "openwebui-postgres:/tmp/middleware.dump" $mwDump
    docker exec openwebui-postgres rm /tmp/middleware.dump

    $manifest.components.middleware_db.size_bytes = (Get-Item $mwDump).Length
    $manifest.components.middleware_db.sha256     = Get-Sha256 $mwDump
    $manifest.components.middleware_db.status     = "ok"
    Write-Log "INFO" ("middleware DB dump OK - " + [math]::Round((Get-Item $mwDump).Length / 1MB, 2) + " MB")
} catch {
    Write-Log "ERROR" "middleware DB dump failed: $_"
    $manifest.components.middleware_db.status = "failed"
    $manifest.error = "middleware_db dump failed: $_"
    Save-Manifest
    exit 1
}
Save-Manifest

# Step 3: Record counts for post-restore verification
try {
    $userCount  = docker exec openwebui-postgres psql -U openwebui_user -d middleware -tAc "SELECT COUNT(*) FROM mw_users;"
    $auditCount = docker exec openwebui-postgres psql -U openwebui_user -d middleware -tAc "SELECT COUNT(*) FROM mw_audit_log;"
    $manifest.record_counts = [ordered]@{
        mw_users     = [int]($userCount.Trim())
        mw_audit_log = [int]($auditCount.Trim())
    }
    Write-Log "INFO" ("Record counts: mw_users=" + $manifest.record_counts.mw_users + " mw_audit_log=" + $manifest.record_counts.mw_audit_log)
} catch {
    Write-Log "WARN" "Could not capture record counts: $_"
}
Save-Manifest

# Step 4: Archive openwebui_data volume
$volArchive = Join-Path $PackageDir "openwebui_data.tar.gz"

if ($SkipVolumeBackup) {
    Write-Log "WARN" "-SkipVolumeBackup flag set - skipping openwebui_data volume archive."
    $manifest.components.data_volume.status = "skipped"
    Save-Manifest
} else {
    Write-Log "INFO" "Archiving openwebui_data volume (pausing open-webui briefly)..."
    $appWasRunning = Get-ContainerRunning "openwebui-app"
    try {
        if ($appWasRunning) {
            Write-Log "INFO" "Pausing openwebui-app for consistent volume snapshot..."
            docker pause openwebui-app | Out-Null
        }

        # Use a temporary alpine container to tar the volume
        $PackageDirEscaped = $PackageDir.Replace('\', '/')
        docker run --rm -v "openwebui_clone_openwebui_data:/data:ro" -v "${PackageDir}:/backup" alpine tar czf /backup/openwebui_data.tar.gz -C /data .

        if ($appWasRunning) {
            docker unpause openwebui-app | Out-Null
            Write-Log "INFO" "openwebui-app unpaused."
        }

        $manifest.components.data_volume.size_bytes = (Get-Item $volArchive).Length
        $manifest.components.data_volume.sha256     = Get-Sha256 $volArchive
        $manifest.components.data_volume.status     = "ok"
        Write-Log "INFO" ("Volume archive OK - " + [math]::Round((Get-Item $volArchive).Length / 1MB, 2) + " MB")
    } catch {
        if ($appWasRunning) {
            try { docker unpause openwebui-app | Out-Null } catch {}
        }
        Write-Log "ERROR" "Volume archive failed: $_"
        $manifest.components.data_volume.status = "failed"
        $manifest.error = "data_volume archive failed: $_"
        Save-Manifest
        exit 1
    }
    Save-Manifest
}

# Step 5: Finalise manifest
$manifest.complete     = $true
$manifest.completed_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$manifest.error        = $null
Save-Manifest

Write-Log "OK" "Backup package complete: $PackageName"
Write-Host ""
Write-Host "Backup complete!" -ForegroundColor Green
Write-Host "   Package: $PackageDir" -ForegroundColor Cyan

# Step 6: Optional secondary copy
if ($SecondaryDest) {
    Write-Log "INFO" "Copying package to secondary destination: $SecondaryDest"
    try {
        $destPackage = Join-Path $SecondaryDest $PackageName
        Copy-Item -Path $PackageDir -Destination $destPackage -Recurse -Force
        Write-Log "INFO" "Secondary copy complete: $destPackage"
        Write-Host "   Secondary copy: $destPackage" -ForegroundColor Cyan
    } catch {
        Write-Log "WARN" "Secondary copy failed (local backup intact): $_"
        Write-Host "WARNING: Secondary copy failed - local backup is intact." -ForegroundColor Yellow
        # Record secondary failure in manifest but do NOT mark complete=false
        $mfContent = Get-Content (Join-Path $PackageDir "manifest.json") | ConvertFrom-Json
        $mfContent | Add-Member -NotePropertyName "secondary_copy_error" -NotePropertyValue "$_" -Force
        $mfContent | ConvertTo-Json -Depth 10 | Set-Content -Path (Join-Path $PackageDir "manifest.json") -Encoding UTF8
    }
}

# Step 7: Retention cleanup
Write-Log "INFO" "Retention cleanup: removing packages older than $RetentionDays days..."
$cutoff = (Get-Date).AddDays(-$RetentionDays)
$oldPackages = Get-ChildItem -Path $BackupRoot -Directory -Filter "backup_*" | Where-Object { $_.LastWriteTime -lt $cutoff }
foreach ($pkg in $oldPackages) {
    $mfPath = Join-Path $pkg.FullName "manifest.json"
    if (Test-Path $mfPath) {
        $oldMf = Get-Content $mfPath | ConvertFrom-Json
        if ($oldMf.complete -eq $true) {
            Remove-Item $pkg.FullName -Recurse -Force
            Write-Log "INFO" "Retention: deleted old package $($pkg.Name)"
        } else {
            Write-Log "WARN" "Retention: skipping incomplete package $($pkg.Name) (preserved for diagnostics)"
        }
    }
}

# Summary
Write-Host ""
Write-Host "Package summary:" -ForegroundColor Cyan
$mfFinal = Get-Content (Join-Path $PackageDir "manifest.json") | ConvertFrom-Json
foreach ($compEntry in $mfFinal.components.PSObject.Properties | Where-Object { $_.MemberType -eq "NoteProperty" }) {
    $comp = $compEntry.Value
    if ($null -ne $comp.size_bytes -and $comp.size_bytes -gt 0) {
        $sz = "$([math]::Round($comp.size_bytes / 1MB, 2)) MB"
    } else {
        $sz = "n/a"
    }
    Write-Host "   $($compEntry.Name): $($comp.status)  $sz" -ForegroundColor White
}
Write-Host ""
