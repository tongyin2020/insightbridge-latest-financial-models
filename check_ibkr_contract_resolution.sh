#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
export IB_CLIENT_ID="${IB_CLIENT_ID:-101}"

"$PY" "$BASE/check_ibkr_contract_resolution.py"
