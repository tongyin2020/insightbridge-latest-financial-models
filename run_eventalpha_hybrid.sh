#!/bin/bash
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON:-python3}"

cd "$BASE"
"$PY" "$BASE/run_eventalpha_hybrid.py" "$@"

