#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
export IB_CLIENT_ID="${IB_CLIENT_ID:-103}"

"$PYTHON_BIN" "$BASE/check_ibkr_market_data_matrix.py"
