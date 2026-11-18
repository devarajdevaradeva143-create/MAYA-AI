#!/usr/bin/env bash
# Maya AI — OpenJarvis safe update (Fedora / Linux)
# Usage: bash scripts/update_openjarvis.sh
#        SKIP_DEPS=1 bash scripts/update_openjarvis.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$ROOT/OpenJarvis"
SKIP_DEPS="${SKIP_DEPS:-0}"

if [ ! -d "$REPO/.git" ]; then
    echo "OpenJarvis repo illa: $REPO" >&2
    exit 1
fi

mkdir -p "$ROOT/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
OLD_COMMIT="$(git -C "$REPO" rev-parse --short HEAD)"
echo "$STAMP  $OLD_COMMIT" >> "$ROOT/backups/commits.log"
echo "[1/6] Current commit: $OLD_COMMIT (backup log saved)"

STASHED=0
if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
    echo "[2/6] Local changes found - stash pannuren"
    git -C "$REPO" stash push -m "maya-auto-$STAMP" >/dev/null
    STASHED=1
else
    echo "[2/6] Working tree clean"
fi

BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
echo "[3/6] Fetch + pull ($BRANCH)"
git -C "$REPO" fetch origin
git -C "$REPO" pull --ff-only origin "$BRANCH"

PATCH_DIR="$ROOT/patches"
shopt -s nullglob
PATCHES=("$PATCH_DIR"/*.patch)
if [ ${#PATCHES[@]} -gt 0 ]; then
    for p in "${PATCHES[@]}"; do
        echo "[4/6] Patch apply: $(basename "$p")"
        git -C "$REPO" apply "$p"
    done
else
    echo "[4/6] Patch illa"
fi

if [ "$STASHED" -eq 1 ]; then
    echo "[5/6] Stash restore"
    git -C "$REPO" stash pop
else
    echo "[5/6] Stash restore venam"
fi

if [ "$SKIP_DEPS" -eq 0 ]; then
    if command -v uv >/dev/null 2>&1; then
        echo "[6/6] Dependencies sync (uv sync --extra dev)"
        (cd "$REPO" && uv sync --extra dev)
    else
        echo "[6/6] uv illa - dependencies skip. Install: https://docs.astral.sh/uv/"
    fi
else
    echo "[6/6] Deps skip (SKIP_DEPS=1)"
fi

NEW_COMMIT="$(git -C "$REPO" rev-parse --short HEAD)"
echo ""
echo "Done! $OLD_COMMIT -> $NEW_COMMIT"
echo "Rollback: git -C \"$REPO\" checkout $OLD_COMMIT"
