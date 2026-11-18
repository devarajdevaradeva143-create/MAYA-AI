#!/usr/bin/env bash
# Maya AI Launcher — Fedora / Linux (bash)
#
# Usage:
#   ./MAYA AI/scripts/maya-launch.sh chat
#   ./MAYA AI/scripts/maya-launch.sh config
#   ./MAYA AI/scripts/maya-launch.sh wake
#   ./MAYA AI/scripts/maya-launch.sh tray
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAYA_MAYA="$PROJECT_ROOT/JARVIS"
PYTHON_EXE="$MAYA_MAYA/.venv-engine/bin/python"

if [[ ! -x "$PYTHON_EXE" ]]; then
    echo "Error: Python not found at $PYTHON_EXE" >&2
    echo "Run: cd JARVIS && uv sync --frozen" >&2
    exit 1
fi

# Set working directory to JARVIS so custom/ package is importable
cd "$MAYA_MAYA"

ARGS=("${@:---help}")

exec "$PYTHON_EXE" -m custom.cli "${ARGS[@]}"
