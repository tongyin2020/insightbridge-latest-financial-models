#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

"$PY" "$BASE/check_dukascopy_demo_setup.py" "$@"
