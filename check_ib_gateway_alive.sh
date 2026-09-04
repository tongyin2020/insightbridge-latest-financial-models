#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

echo "===== IB Gateway Runtime ====="
"$PY" "$BASE/check_ibkr_gateway_runtime.py"

echo
echo "===== IBKR Financial Runtime ====="
"$PY" "$BASE/check_five_models_runtime_health.py"
