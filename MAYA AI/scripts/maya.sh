#!/usr/bin/env bash
# Maya AI launcher (Fedora / Linux)
#
# Usage:
#   bash "MAYA AI/scripts/maya.sh" chat
#   bash "MAYA AI/scripts/maya.sh" todo add "Buy milk"
#
# Runs the custom CLI with the same Python 3.13 interpreter as the engine.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MAYA="$ROOT/JARVIS"

if [ ! -d "$MAYA" ]; then
  echo "JARVIS folder not found at $MAYA" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

cd "$MAYA"
exec uv run --python 3.13 maya "$@"
