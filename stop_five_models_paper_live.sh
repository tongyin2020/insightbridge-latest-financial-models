#!/bin/zsh

set -euo pipefail

PLIST="/Users/tongyin/Library/LaunchAgents/com.insightbridge.five-models.paper.plist"

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
echo "Stopped: com.insightbridge.five-models.paper"
