# Maya AI launcher (Windows / PowerShell)
#
# Usage:
#   .\MAYA AI\scripts\maya.ps1 chat
#   .\MAYA AI\scripts\maya.ps1 todo add "Buy milk"
#   .\MAYA AI\scripts\maya.ps1 monitor status
#
# Runs the custom CLI with the same Python 3.13 interpreter as the engine.

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$maya = Join-Path $root "JARVIS"

if (-not (Test-Path $maya)) {
    Write-Error "JARVIS folder not found at $maya"
    exit 1
}

Push-Location $maya
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Error "uv not found. Install uv first: https://docs.astral.sh/uv/"
        exit 1
    }
    uv run --python 3.13 maya @Rest
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
