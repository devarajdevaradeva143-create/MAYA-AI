#!/usr/bin/env bash
# Maya AI — Fedora systemd user service installer.
#
# Installs maya.service as a *user* service (no root, no sudo).
#
# Usage:
#   bash "LAPTOP/fedora/app/install_service.sh"
#
# Status / logs:
#   systemctl --user status maya.service
#   journalctl --user -u maya.service -f
#
# Uninstall:
#   systemctl --user disable --now maya.service
#   rm ~/.config/systemd/user/maya.service

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$APP_DIR/../../.." && pwd)"
UNIT_SRC="$APP_DIR/maya.service"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_DST="$UNIT_DIR/maya.service"

if [ ! -f "$UNIT_SRC" ]; then
  echo "maya.service not found at $UNIT_SRC" >&2
  exit 1
fi

if [ ! -d "$ROOT/JARVIS" ]; then
  echo "JARVIS folder not found at $ROOT/JARVIS" >&2
  exit 1
fi

if [ ! -x "$ROOT/JARVIS/.venv/bin/python" ]; then
  echo "Python venv missing: $ROOT/JARVIS/.venv/bin/python" >&2
  echo "Run first:  cd \"$ROOT/JARVIS\" && uv sync" >&2
  exit 1
fi

mkdir -p "$UNIT_DIR"

# Rewrite the %h-based paths to this machine's real project path, so the unit
# works even when the project is not in ~/Desktop.
python_bin="$ROOT/JARVIS/.venv/bin/python"
sed -e "s|^WorkingDirectory=.*|WorkingDirectory=$ROOT/JARVIS|" \
    -e "s|^ExecStart=.*|ExecStart=$python_bin -m custom.cli monitor start|" \
    "$UNIT_SRC" > "$UNIT_DST"

systemctl --user daemon-reload
systemctl --user enable --now maya.service

echo "Installed: $UNIT_DST"
echo "  status: systemctl --user status maya.service"
echo "  logs:   journalctl --user -u maya.service -f"
echo "  remove: systemctl --user disable --now maya.service && rm \"$UNIT_DST\""
