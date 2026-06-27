#!/bin/bash
set -euo pipefail

BASE="/Users/tongyin/Desktop/Test"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" "$BASE/run_eventalpha_testkit_once.py" \
  --csv "$BASE/decisions.csv" \
  --output "$BASE/results" \
  --mode "${1:-ibm-suite}" \
  --preset "${2:-quick}"
