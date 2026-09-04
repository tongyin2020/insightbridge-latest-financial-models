#!/bin/bash
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
RUNTIME_DIR="$BASE/ibkr_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/ib_gateway.pid"
LAUNCH_LOG="$LOG_DIR/ib_gateway_launch.log"
APPLICATIONS_DIR="/Users/tongyin/Applications"

resolve_gateway_version() {
  if [[ -n "${IB_GATEWAY_VERSION:-}" ]]; then
    echo "${IB_GATEWAY_VERSION}"
    return 0
  fi

  local latest
  latest="$(
    find "$APPLICATIONS_DIR" -maxdepth 1 -type d -name 'IB Gateway 10.*' 2>/dev/null \
      | sort -V \
      | tail -n 1
  )"

  if [[ -z "$latest" ]]; then
    return 1
  fi

  basename "$latest" | sed 's/^IB Gateway //'
}

"$PY" "$BASE/prepare_ibkr_paper_runtime.py" >/dev/null

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "IBKR paper gateway already running with PID $OLD_PID"
    exit 0
  fi
fi

if ! GATEWAY_VERSION="$(resolve_gateway_version)"; then
  echo "No installed IB Gateway 10.x folder found under $APPLICATIONS_DIR"
  exit 1
fi

echo "Using IB Gateway version $GATEWAY_VERSION"

nohup "$BASE/third_party/IBC/resources/scripts/ibcstart.sh" \
  "$GATEWAY_VERSION" \
  --gateway \
  --tws-path="$APPLICATIONS_DIR" \
  --tws-settings-path="$RUNTIME_DIR/ib_settings/paper" \
  --ibc-path="$BASE/third_party/IBC/resources" \
  --ibc-ini="$RUNTIME_DIR/private/config.paper.ini" \
  --mode=paper \
  --on2fatimeout=restart \
  >"$LAUNCH_LOG" 2>&1 &

sleep 2
REAL_PID="$(pgrep -f 'ibcalpha.ibc.IbcGateway' | tail -n 1 || true)"
if [[ -n "$REAL_PID" ]]; then
  echo "$REAL_PID" > "$PID_FILE"
else
  echo $! > "$PID_FILE"
fi
echo "started ibkr paper gateway pid=$(cat "$PID_FILE")"
echo "launch_log: $LAUNCH_LOG"
