#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
LABEL="com.insightbridge.ibkr.paper.gateway"
PID_FILE="$BASE/ibkr_runtime/ib_gateway.pid"
ENSURE_SCRIPT="$BASE/ensure_ib_gateway.sh"

echo "Restarting IB Gateway..."

launchctl kickstart -k "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true

sleep 3

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "IB Gateway restarted: PID $PID"
  else
    echo "LaunchAgent kickstart did not confirm a live PID yet."
  fi
else
  echo "PID file not present yet after restart attempt."
fi

echo "Running unified watchdog recovery..."
bash "$ENSURE_SCRIPT" || true

echo
bash "$BASE/check_ibkr_gateway_runtime.sh" || true
