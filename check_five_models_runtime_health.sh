#!/bin/zsh
set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
PY="/opt/anaconda3/bin/python3"

"$PY" "$BASE/check_five_models_runtime_health.py" "$@"
