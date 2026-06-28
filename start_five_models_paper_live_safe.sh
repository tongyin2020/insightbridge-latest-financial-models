#!/bin/zsh

set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_GitHubSync_Latest"
PY="/opt/anaconda3/bin/python3"
LOG_DIR="$BASE/reports/runtime"
LOG_FILE="$LOG_DIR/five_models_paper_live.log"
PID_FILE="$LOG_DIR/five_models_paper_live.pid"

mkdir -p "$LOG_DIR"

SYMBOLS="EURUSD,USDJPY,MES,MNQ,ZT,ZN"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Already running: PID $OLD_PID"
    echo "log: $LOG_FILE"
    exit 0
  fi
fi

nohup "$PY" -u "$BASE/execution_framework/run_tws_continuous.py" \
  --live \
  --symbols "$SYMBOLS" \
  --interval 60 \
  --broker-source-of-truth \
  > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

echo "Started five-model paper runtime."
echo "pid: $(cat "$PID_FILE")"
echo "symbols: $SYMBOLS"
echo "log: $LOG_FILE"
