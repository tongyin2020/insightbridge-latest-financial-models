#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
BASE="$IBREPO"
PY="/opt/anaconda3/bin/python3"

EVENT_TYPE="${1:-cpi}"
TITLE="${2:-Manual EventAlpha paper run}"
TOP_N="${3:-2}"
TELEGRAM_FLAG="${4:---no-telegram-alerts}"

"$PY" "$BASE/run_eventalpha_paper.py" --event-type "$EVENT_TYPE" --title "$TITLE" --top-n "$TOP_N" "$TELEGRAM_FLAG"
