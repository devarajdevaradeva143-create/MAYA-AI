# Maya AI — Windows autostart installer
#
# Registers a Task Scheduler job that starts the Maya tray app at logon.
#
# Usage (normal PowerShell, no admin needed for current-user task):
#   powershell -ExecutionPolicy Bypass -File "LAPTOP\windows\app\install_autostart.ps1"
#
# Uninstall:
#   Unregister-ScheduledTask -TaskName "MayaAI" -Confirm:$false

$ErrorActionPreference = "Stop"

$appDir = $PSScriptRoot
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $appDir))
$tray = Join-Path $appDir "maya_tray.py"
$pythonw = Join-Path $root "JARVIS\.venv\Scripts\pythonw.exe"
$taskName = "MayaAI"

if (-not (Test-Path $tray)) {
    Write-Error "maya_tray.py not found at $tray"
    exit 1
}

if (-not (Test-Path $pythonw)) {
    # Fall back to the engine venv, then to the system python.
    $pythonw = Join-Path $root "JARVIS\.venv-engine\Scripts\pythonw.exe"
}
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
}
if (-not $pythonw) {
    Write-Error "pythonw.exe not found. Install the Maya Python env first (uv sync)."
    exit 1
}

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$tray`"" -WorkingDirectory $appDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Maya AI tray app (local assistant)" -Force | Out-Null

Write-Host "Autostart installed: task '$taskName'"
Write-Host "  runs: $pythonw `"$tray`""
Write-Host "  remove: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
