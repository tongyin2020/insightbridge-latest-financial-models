#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
TARGET="$HOME/Library/LaunchAgents/com.insightbridge.dukascopy.fx.bridge.plist"
LOG_DIR="$BASE/reports/dukascopy_bridge"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
cp "$BASE/com.insightbridge.dukascopy.fx.bridge.plist" "$TARGET"
launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/com.insightbridge.dukascopy.fx.bridge"
launchctl kickstart -k "gui/$(id -u)/com.insightbridge.dukascopy.fx.bridge" >/dev/null 2>&1 || true

echo "installed launchagent: $TARGET"
