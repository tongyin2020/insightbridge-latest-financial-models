#!/bin/bash
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PY="${PYTHON:-python3}"

cd "$BASE"
"$PY" "$BASE/run_eventalpha_hybrid.py" "$@"

