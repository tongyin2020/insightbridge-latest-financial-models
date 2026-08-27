#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO/03_FX_AUD_NZD_EUR_GBP/fx_trading_system/adapters/dukascopy"

cd "$BASE"
STRATEGY_SOURCE="DukascopyTickProbeStrategy.java" \
JAR_NAME="dukascopy-tick-probe.jar" \
bash ./build.sh

echo
echo "Probe JAR ready:"
echo "${BASE}/dukascopy-tick-probe.jar"
