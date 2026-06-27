#!/bin/bash
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

"$PYTHON_BIN" "$BASE/run_eventalpha_massive_history_quantum_once.py" "$@"
