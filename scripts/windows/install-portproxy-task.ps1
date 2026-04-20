# Register update-portproxy.ps1 as a Windows Scheduled Task that runs
# at every system start. After this, WSL's port forward auto-heals
# across Windows reboots — you don't need to re-run anything manually.
#
# Run this ONCE from elevated PowerShell. Idempotent — re-running updates.

param(
    [string]$ScriptPath = (Join-Path $PSScriptRoot "update-portproxy.ps1"),
    [string]$TaskName   = "WSL SSH Portproxy Refresh"
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "must run from an elevated (Administrator) PowerShell" }

if (-not (Test-Path $ScriptPath)) { throw "script not found: $ScriptPath" }

$action    = New-ScheduledTaskAction -Execute "PowerShell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger   = New-ScheduledTaskTrigger -AtStartup
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries -StartWhenAvailable `
                -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null

Write-Host "[install] registered task: $TaskName"
Write-Host "[install] running it now so the current portproxy is valid..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2
Write-Host "[install] done. Check state: Get-ScheduledTaskInfo -TaskName '$TaskName'"
