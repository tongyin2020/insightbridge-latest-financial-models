#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO

set -euo pipefail

BASE="$IBREPO"
PY="/opt/anaconda3/bin/python3"
SCRIPT="$BASE/execution_framework/run_tws_continuous.py"
PORT="4002"
SYMBOLS="BTC,EURUSD,USDJPY,MES,MNQ,CL,ZT,ZN,SR3"

export HOME="/Users/tongyin"
export USER="tongyin"
export LOGNAME="tongyin"
export SHELL="/bin/zsh"
export PATH="/opt/anaconda3/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED="1"

cd "$BASE"

exec "$PY" -u "$SCRIPT" \
  --live \
  --port "$PORT" \
  --symbols "$SYMBOLS" \
  --interval 60 \
  --broker-source-of-truth
