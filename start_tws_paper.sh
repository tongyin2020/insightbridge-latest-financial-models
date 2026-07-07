#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
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
echo "bash $IBREPO/check_tws_paper_channel.sh"
