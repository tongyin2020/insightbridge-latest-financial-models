#!/bin/zsh
set -euo pipefail

APP="/Users/tongyin/Applications/Trader Workstation/Trader Workstation.app"

if [[ ! -d "$APP" ]]; then
  echo "TWS app not found: $APP"
  exit 1
fi

open -a "$APP"
echo "TWS launched."
echo "Please log into the Paper Trading account in TWS, then keep TWS open."
echo "After login, run:"
echo "bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_tws_paper_channel.sh"
