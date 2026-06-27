#!/bin/bash
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

"$PY" "$BASE/run_eventalpha_real_history_validation.py" "$@"
