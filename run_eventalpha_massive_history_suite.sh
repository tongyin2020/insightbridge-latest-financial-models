#!/bin/bash
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

START_YEAR="${START_YEAR:-2018}"
END_YEAR="${END_YEAR:-2025}"
TOP_N="${TOP_N:-3}"
MAX_EIA_CASES="${MAX_EIA_CASES:-240}"
TOP_K="${TOP_K:-3}"
RISK_BUDGET="${RISK_BUDGET:-2.5}"

echo "EventAlpha Massive Real-History Suite"
echo "============================================================"
echo "start_year: ${START_YEAR}"
echo "end_year: ${END_YEAR}"
echo "top_n: ${TOP_N}"
echo "max_eia_cases: ${MAX_EIA_CASES}"
echo "top_k: ${TOP_K}"
echo "risk_budget: ${RISK_BUDGET}"
echo "------------------------------------------------------------"

"$PY" "$BASE/run_eventalpha_real_history_validation.py" \
  --start-year "${START_YEAR}" \
  --end-year "${END_YEAR}" \
  --top-n "${TOP_N}" \
  --max-eia-cases "${MAX_EIA_CASES}"

"$PY" "$BASE/build_eventalpha_real_history_quantum_pack.py" \
  --top-k "${TOP_K}" \
  --risk-budget "${RISK_BUDGET}"

echo "------------------------------------------------------------"
echo "Massive real-history validation + quantum pack build complete."
