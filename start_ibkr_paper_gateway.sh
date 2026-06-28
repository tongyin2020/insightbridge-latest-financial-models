#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
RUNTIME_DIR="$BASE/ibkr_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
PID_FILE="$RUNTIME_DIR/ib_gateway.pid"
LAUNCH_LOG="$LOG_DIR/ib_gateway_launch.log"

"$PY" "$BASE/prepare_ibkr_paper_runtime.py" >/dev/null

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "IBKR paper gateway already running with PID $OLD_PID"
    exit 0
  fi
fi

nohup "$BASE/third_party/IBC/resources/scripts/ibcstart.sh" \
  10.45 \
  --gateway \
  --tws-path="/Users/tongyin/Applications" \
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
