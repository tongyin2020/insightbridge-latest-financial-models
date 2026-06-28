#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
export IB_CLIENT_ID="${IB_CLIENT_ID:-101}"

if ! "$PY" "$BASE/check_tws_paper_channel.py"; then
  echo
  echo "TWS paper channel is not ready yet."
  echo "1. Open TWS paper account"
  echo "2. Confirm API port 7497 is enabled"
  echo "3. Re-run this script"
  exit 1
fi

cd "$BASE/02_StockIndex_IBKR_ES_NQ"
"$PY" live_trader.py
