# Maya AI Launcher — Windows (PowerShell)
#
# Usage:
#   .\MAYA AI\scripts\maya-launch.ps1 chat
#   .\MAYA AI\scripts\maya-launch.ps1 config
#   .\MAYA AI\scripts\maya-launch.ps1 wake
#   .\MAYA AI\scripts\maya-launch.ps1 tray
#

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
$mayaMaya = Join-Path $projectRoot "JARVIS"
$pythonExe = Join-Path $mayaMaya ".venv-engine\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python not found at $pythonExe. Run: cd JARVIS && uv sync --frozen"
    exit 1
}

# Set working directory to JARVIS so custom/ package is importable
Push-Location $mayaMaya

$args = $args
if ($args.Count -eq 0) {
    $args = @("--help")
}

& $pythonExe -m custom.cli $args

Pop-Location
