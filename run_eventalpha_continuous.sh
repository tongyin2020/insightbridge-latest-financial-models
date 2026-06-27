#!/bin/zsh
BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="/opt/anaconda3/bin/python3"

ACTION="${1:-start}"
shift || true

"$PY" "$BASE/manage_eventalpha_runtime.py" "$ACTION" "$@"
