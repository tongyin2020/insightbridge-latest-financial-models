#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
export IB_CLIENT_ID="${IB_CLIENT_ID:-101}"

"$PY" "$BASE/check_ibkr_contract_resolution.py"
