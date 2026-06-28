#!/bin/zsh
set -euo pipefail

TARGET="$HOME/Library/LaunchAgents/com.insightbridge.ibkr.paper.gateway.plist"

launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
rm -f "$TARGET"
echo "removed launchagent: $TARGET"
