#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
LABEL="com.insightbridge.dukascopy.fx.bridge"
START_SCRIPT="$BASE/start_dukascopy_fx_bridge_backend.sh"

echo "Restarting Dukascopy FX bridge backend..."

launchctl kickstart -k "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true

sleep 3

if ! /usr/bin/curl -fsS "http://127.0.0.1:8001/api/health" >/dev/null 2>&1; then
  echo "Dukascopy backend API is still down. Falling back to project start script..."
  bash "$START_SCRIPT" || true
  sleep 3
fi

echo
python3 "$BASE/check_dukascopy_fx_bridge_status.py" || true

echo
echo "Note: if the backend is live but adapter is idle, JForex strategy also needs to be running."
