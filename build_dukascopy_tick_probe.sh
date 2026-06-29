#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/03_FX_AUD_NZD_EUR_GBP/fx_trading_system/adapters/dukascopy"

cd "$BASE"
STRATEGY_SOURCE="DukascopyTickProbeStrategy.java" \
JAR_NAME="dukascopy-tick-probe.jar" \
bash ./build.sh

echo
echo "Probe JAR ready:"
echo "${BASE}/dukascopy-tick-probe.jar"
