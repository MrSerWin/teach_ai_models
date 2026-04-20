# Rebind Windows-side port-forward 0.0.0.0:<ListenPort>  ->  <current-WSL-IP>:<ConnectPort>.
# WSL's internal IP changes on every Windows reboot, so any existing rule goes stale.
# Run this ad-hoc from elevated PowerShell, OR install it as a scheduled task
# via install-portproxy-task.ps1 so it fires automatically at boot.
#
# Requires: Administrator privileges (netsh portproxy + firewall rules).

param(
    [int]$ListenPort  = 22,
    [int]$ConnectPort = 2222,
    [string]$Distro   = ""    # optional; if set, queries that specific WSL distro
)

$ErrorActionPreference = "Stop"

function Log { param([string]$m) Write-Host "[portproxy] $m" }

# 1. Must be admin.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "must run from an elevated (Administrator) PowerShell" }

# 2. Current WSL IP.
$wslCmd = if ($Distro) { "wsl -d $Distro hostname -I" } else { "wsl hostname -I" }
$wslIp  = (Invoke-Expression $wslCmd).Trim().Split()[0]
if (-not $wslIp) { throw "could not determine WSL IP (is WSL installed / started?)" }
Log "WSL IP: $wslIp"

# 3. Remove any existing rule for this listen port (idempotent).
$existing = netsh interface portproxy show v4tov4 | Select-String "^\s*\S+\s+$ListenPort\s"
if ($existing) {
    Log "removing stale rule on port $ListenPort"
    netsh interface portproxy delete v4tov4 listenport=$ListenPort listenaddress=0.0.0.0 | Out-Null
}

# 4. Add new rule.
Log "adding: 0.0.0.0:$ListenPort -> ${wslIp}:$ConnectPort"
netsh interface portproxy add v4tov4 `
    listenport=$ListenPort `
    listenaddress=0.0.0.0 `
    connectport=$ConnectPort `
    connectaddress=$wslIp | Out-Null

# 5. Ensure firewall allows inbound on ListenPort.
$ruleName = "WSL SSH (port $ListenPort)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    Log "adding firewall rule: $ruleName"
    New-NetFirewallRule -DisplayName $ruleName `
        -Direction Inbound -LocalPort $ListenPort `
        -Protocol TCP -Action Allow | Out-Null
}

Log "done. current state:"
netsh interface portproxy show v4tov4
