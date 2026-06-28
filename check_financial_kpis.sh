#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "InsightBridge Financial KPI Check"
echo "============================================================"
"$PYTHON_BIN" "$BASE/analyze_eventalpha_financial_kpis.py"
