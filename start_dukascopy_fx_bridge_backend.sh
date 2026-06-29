#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/03_FX_AUD_NZD_EUR_GBP/backend"
PROJECT_BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
LOG_DIR="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/dukascopy_bridge"
PID_FILE="${LOG_DIR}/dukascopy_fx_backend.pid"
LOG_FILE="${LOG_DIR}/dukascopy_fx_backend.log"
HEALTH_URL="http://127.0.0.1:8001/api/health"

export DUKASCOPY_FX_PAIRS="${DUKASCOPY_FX_PAIRS:-AUD/USD,NZD/USD,EUR/USD,USD/JPY,GBP/USD,AUD/JPY,NZD/JPY}"
export PYTHONPATH="${PROJECT_BASE}:${PYTHONPATH:-}"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    if /usr/bin/curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      echo "Backend already running: PID ${OLD_PID}"
      echo "api: ${HEALTH_URL}"
      echo "log: ${LOG_FILE}"
      exit 0
    fi
  fi
  rm -f "$PID_FILE"
fi

cd "$BASE"
nohup "$PY" server.py > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

for _ in {1..20}; do
  sleep 1
  if /usr/bin/curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Dukascopy FX bridge backend started."
    echo "pid: $(cat "$PID_FILE")"
    echo "api: ${HEALTH_URL}"
    echo "log: ${LOG_FILE}"
    exit 0
  fi
done

echo "Backend failed to become healthy."
echo "pid_file: ${PID_FILE}"
echo "log: ${LOG_FILE}"
tail -n 40 "$LOG_FILE" 2>/dev/null || true
exit 1
