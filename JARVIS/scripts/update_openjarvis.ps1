# Maya AI — OpenJarvis safe update (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\update_openjarvis.ps1
#        powershell ... -SkipDeps

param(
    [switch]$SkipDeps,
    [string]$Repo = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Repo)) { $Repo = Join-Path $root "OpenJarvis" }

if (-not (Test-Path (Join-Path $Repo ".git"))) {
    Write-Error "OpenJarvis repo illa: $Repo"
    exit 1
}

$backupDir = Join-Path $root "backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$oldCommit = (git -C $Repo rev-parse --short HEAD).Trim()
"$stamp  $oldCommit" | Out-File (Join-Path $backupDir "commits.log") -Append
Write-Host "[1/6] Current commit: $oldCommit (backup log saved)"

$status = git -C $Repo status --porcelain
$stashed = $false
if ($status) {
    Write-Host "[2/6] Local changes found - stash pannuren"
    git -C $Repo stash push -m "maya-auto-$stamp" | Out-Null
    $stashed = $true
} else {
    Write-Host "[2/6] Working tree clean"
}

$branch = (git -C $Repo rev-parse --abbrev-ref HEAD).Trim()
Write-Host "[3/6] Fetch + pull ($branch)"
git -C $Repo fetch origin
git -C $Repo pull --ff-only origin $branch

$patchDir = Join-Path $root "patches"
$patches = @()
if (Test-Path $patchDir) {
    $patches = Get-ChildItem $patchDir -Filter *.patch -File -ErrorAction SilentlyContinue | Sort-Object Name
}
if ($patches.Count -gt 0) {
    foreach ($p in $patches) {
        Write-Host "[4/6] Patch apply: $($p.Name)"
        git -C $Repo apply $p.FullName
    }
} else {
    Write-Host "[4/6] Patch illa"
}

if ($stashed) {
    Write-Host "[5/6] Stash restore"
    git -C $Repo stash pop
} else {
    Write-Host "[5/6] Stash restore venam"
}

if (-not $SkipDeps) {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "[6/6] Dependencies sync (uv sync --extra dev)"
        Push-Location $Repo
        try { uv sync --extra dev } finally { Pop-Location }
    } else {
        Write-Host "[6/6] uv illa - dependencies skip. Install: https://docs.astral.sh/uv/"
    }
} else {
    Write-Host "[6/6] Deps skip (-SkipDeps)"
}

$newCommit = (git -C $Repo rev-parse --short HEAD).Trim()
Write-Host ""
Write-Host "Done! $oldCommit -> $newCommit"
Write-Host "Rollback: git -C `"$Repo`" checkout $oldCommit"
