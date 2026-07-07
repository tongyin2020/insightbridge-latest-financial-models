#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
BASE="$IBREPO"
PY="/opt/anaconda3/bin/python3"

ACTION="${1:-start}"
shift || true

"$PY" "$BASE/manage_eventalpha_runtime.py" "$ACTION" "$@"
