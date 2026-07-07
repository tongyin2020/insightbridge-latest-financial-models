#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
export IB_CLIENT_ID="${IB_CLIENT_ID:-103}"

"$PYTHON_BIN" "$BASE/check_ibkr_market_data_matrix.py"
