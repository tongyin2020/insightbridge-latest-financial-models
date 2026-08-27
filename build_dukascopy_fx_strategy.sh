#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

SCRIPT="$IBREPO/03_FX_AUD_NZD_EUR_GBP/fx_trading_system/adapters/dukascopy/build.sh"

bash "$SCRIPT"
