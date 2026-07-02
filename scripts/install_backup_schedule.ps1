#!/usr/bin/env powershell
# ==============================================================================
# Script: install_backup_schedule.ps1
# Description: Idempotently install, update, or remove a Windows Task Scheduler
#              daily backup task for OpenWebUI.
#
# Usage:
#   # Install or update daily backup at 02:00 AM:
#   .\scripts\install_backup_schedule.ps1
#
#   # Specify a different time:
#   .\scripts\install_backup_schedule.ps1 -TriggerTime "03:30"
#
#   # Pass extra parameters to backup_db.ps1:
#   .\scripts\install_backup_schedule.ps1 -BackupArgs "-RetentionDays 14 -SecondaryDest \\nas\backups"
#
#   # Remove the scheduled task:
#   .\scripts\install_backup_schedule.ps1 -Uninstall
#
#   # Show task status:
#   .\scripts\install_backup_schedule.ps1 -Status
#
#   # Run the backup immediately (manually):
#   .\scripts\install_backup_schedule.ps1 -RunNow
#
# Notes:
#   - Must be run as Administrator to create/modify scheduled tasks.
#   - Backup logs: <project>\backups\logs\backup_log.jsonl
#   - Task failure signal: Last Run Result != 0 in Task Scheduler.
# ==============================================================================

param (
    [string]$TriggerTime = "02:00",
    [string]$BackupArgs  = "",
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$RunNow
)

$TaskName    = "OpenWebUI-DailyBackup"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$ScriptPath  = Join-Path $ProjectRoot "scripts\backup_db.ps1"
$LogDir      = Join-Path $ProjectRoot "backups\logs"

# Status
if ($Status) {
    Write-Host ""
    Write-Host "=== Task Scheduler Status: $TaskName ===" -ForegroundColor Cyan
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "  Task does not exist." -ForegroundColor Yellow
    } else {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Host "  State      : $($task.State)" -ForegroundColor White
        Write-Host "  Last Run   : $($info.LastRunTime)" -ForegroundColor White
        $rc = $info.LastTaskResult
        $rcColor = if ($rc -eq 0) { "Green" } else { "Yellow" }
        Write-Host "  Last Result: $rc  (0 = success)" -ForegroundColor $rcColor
        Write-Host "  Next Run   : $($info.NextRunTime)" -ForegroundColor White
        Write-Host "  Trigger    : Daily at $TriggerTime" -ForegroundColor Cyan
        Write-Host "  Script     : $ScriptPath" -ForegroundColor Cyan
        Write-Host "  Log        : $LogDir\backup_log.jsonl" -ForegroundColor Cyan
    }
    Write-Host ""
    exit 0
}

# Uninstall
if ($Uninstall) {
    Write-Host ""
    Write-Host "=== Removing task: $TaskName ===" -ForegroundColor Yellow
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  Task removed." -ForegroundColor Green
    } else {
        Write-Host "  Task not found - nothing to remove." -ForegroundColor Yellow
    }
    Write-Host ""
    exit 0
}

# RunNow
if ($RunNow) {
    Write-Host ""
    Write-Host "=== Running backup manually ===" -ForegroundColor Cyan
    if (-not (Test-Path $ScriptPath)) {
        Write-Host "  Backup script not found: $ScriptPath" -ForegroundColor Red
        exit 1
    }
    $argList = "-NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`""
    if ($BackupArgs) { $argList += " $BackupArgs" }
    Write-Host "  Running: powershell $argList" -ForegroundColor White
    $proc = Start-Process powershell -ArgumentList $argList -Wait -PassThru -NoNewWindow
    Write-Host ""
    if ($proc.ExitCode -eq 0) {
        Write-Host "  Backup completed successfully." -ForegroundColor Green
    } else {
        Write-Host "  Backup exited with code $($proc.ExitCode). Check $LogDir\backup_log.jsonl" -ForegroundColor Red
    }
    Write-Host ""
    exit $proc.ExitCode
}

# Install / Update
Write-Host ""
Write-Host "=== Installing/updating task: $TaskName ===" -ForegroundColor Cyan

if (-not (Test-Path $ScriptPath)) {
    Write-Host "  Backup script not found: $ScriptPath" -ForegroundColor Red
    exit 1
}

# Ensure log directory exists and check permissions
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
try {
    $testFile = Join-Path $LogDir ".write_test"
    [System.IO.File]::WriteAllText($testFile, "ok")
    Remove-Item $testFile -Force
    Write-Host "  Log directory writable: $LogDir" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: Log directory may not be writable: $LogDir" -ForegroundColor Yellow
}

# Build action
$argLine = "-NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`""
if ($BackupArgs) { $argLine += " $BackupArgs" }

$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine -WorkingDirectory $ProjectRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At $TriggerTime
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -WakeToRun:$false `
    -MultipleInstances IgnoreNew

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal   = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType S4U -RunLevel Highest

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  Updating existing task..." -ForegroundColor Yellow
    Set-ScheduledTask -TaskName $TaskName `
        -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    Write-Host "  Task updated." -ForegroundColor Green
} else {
    Write-Host "  Creating new task..." -ForegroundColor Cyan
    Register-ScheduledTask -TaskName $TaskName `
        -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description "Daily OpenWebUI production backup (databases + data volume)." | Out-Null
    Write-Host "  Task created." -ForegroundColor Green
}

Write-Host ""
Write-Host "  Task name  : $TaskName" -ForegroundColor White
Write-Host "  Schedule   : Daily at $TriggerTime" -ForegroundColor White
Write-Host "  Script     : $ScriptPath" -ForegroundColor White
Write-Host "  Log        : $LogDir\backup_log.jsonl" -ForegroundColor White
Write-Host ""
Write-Host "  Useful commands:" -ForegroundColor Cyan
Write-Host "    Status  : .\scripts\install_backup_schedule.ps1 -Status" -ForegroundColor White
Write-Host "    Run now : .\scripts\install_backup_schedule.ps1 -RunNow" -ForegroundColor White
Write-Host "    Disable : Disable-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
Write-Host "    Enable  : Enable-ScheduledTask  -TaskName '$TaskName'" -ForegroundColor White
Write-Host "    Remove  : .\scripts\install_backup_schedule.ps1 -Uninstall" -ForegroundColor White
Write-Host ""
Write-Host "  Filesystem permissions:" -ForegroundColor Cyan
Write-Host "    Backup dir ($ProjectRoot\backups): write access for task user" -ForegroundColor White
Write-Host "    Secondary dest (if configured)  : write access for task user" -ForegroundColor White
Write-Host "    Task runs as: $currentUser" -ForegroundColor White
Write-Host ""
