#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

echo "===== Dukascopy LaunchAgent ====="
"$PY" "$BASE/check_dukascopy_fx_launchagent.py" || true

echo
echo "===== Dukascopy FX Bridge ====="
"$PY" "$BASE/check_dukascopy_fx_bridge_status.py"

echo
echo "===== Dukascopy Seven-FX Runtime ====="
"$PY" "$BASE/check_dukascopy_seven_fx_runtime.py"
