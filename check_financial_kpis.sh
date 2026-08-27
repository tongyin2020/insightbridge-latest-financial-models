#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "InsightBridge Financial KPI Check"
echo "============================================================"
"$PYTHON_BIN" "$BASE/analyze_eventalpha_financial_kpis.py"
