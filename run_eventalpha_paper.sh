#!/bin/zsh
BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="/opt/anaconda3/bin/python3"

EVENT_TYPE="${1:-cpi}"
TITLE="${2:-Manual EventAlpha paper run}"
TOP_N="${3:-2}"
TELEGRAM_FLAG="${4:---telegram-alerts}"

"$PY" "$BASE/run_eventalpha_paper.py" --event-type "$EVENT_TYPE" --title "$TITLE" --top-n "$TOP_N" "$TELEGRAM_FLAG"
