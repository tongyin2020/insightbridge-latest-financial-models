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
PROBLEM="${PROBLEM:-asset_subset_selection}"
ASSET="${ASSET:-}"
MODE="${MODE:-aws}"
SHOTS="${SHOTS:-512}"
GRID_POINTS="${GRID_POINTS:-3}"
REPS="${REPS:-1}"
DEVICE_ARN="${DEVICE_ARN:-arn:aws:braket:::device/quantum-simulator/amazon/sv1}"
S3_PREFIX="${S3_PREFIX:-insightbridge-eventalpha-quantum}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start-year) START_YEAR="$2"; shift 2 ;;
    --end-year) END_YEAR="$2"; shift 2 ;;
    --top-n) TOP_N="$2"; shift 2 ;;
    --max-eia-cases) MAX_EIA_CASES="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --risk-budget) RISK_BUDGET="$2"; shift 2 ;;
    --problem) PROBLEM="$2"; shift 2 ;;
    --asset) ASSET="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --shots) SHOTS="$2"; shift 2 ;;
    --grid-points) GRID_POINTS="$2"; shift 2 ;;
    --reps) REPS="$2"; shift 2 ;;
    --device-arn) DEVICE_ARN="$2"; shift 2 ;;
    --s3-prefix) S3_PREFIX="$2"; shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

echo "EventAlpha Massive Real-History + AWS Cross-Check"
echo "============================================================"
echo "start_year: ${START_YEAR}"
echo "end_year: ${END_YEAR}"
echo "top_n: ${TOP_N}"
echo "max_eia_cases: ${MAX_EIA_CASES}"
echo "top_k: ${TOP_K}"
echo "risk_budget: ${RISK_BUDGET}"
echo "problem: ${PROBLEM}"
echo "mode: ${MODE}"
echo "shots: ${SHOTS}"
echo "grid_points: ${GRID_POINTS}"
echo "------------------------------------------------------------"

"$PY" "$BASE/run_eventalpha_real_history_validation.py" \
  --start-year "${START_YEAR}" \
  --end-year "${END_YEAR}" \
  --top-n "${TOP_N}" \
  --max-eia-cases "${MAX_EIA_CASES}"

"$PY" "$BASE/build_eventalpha_real_history_quantum_pack.py" \
  --top-k "${TOP_K}" \
  --risk-budget "${RISK_BUDGET}"

CMD=(
  "$PY" "$BASE/quantum_tools/aws_braket_eventalpha_submit.py"
  --mode "${MODE}"
  --problem "${PROBLEM}"
  --shots "${SHOTS}"
  --grid-points "${GRID_POINTS}"
  --reps "${REPS}"
)

if [[ -n "${ASSET}" ]]; then
  CMD+=(--asset "${ASSET}")
fi

if [[ "${MODE}" == "aws" ]]; then
  CMD+=(--device-arn "${DEVICE_ARN}" --submit-only --s3-prefix "${S3_PREFIX}")
fi

"${CMD[@]}"

echo "------------------------------------------------------------"
echo "Massive real-history AWS cross-check orchestration complete."
