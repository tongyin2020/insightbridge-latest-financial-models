#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
TARGET="$HOME/Library/LaunchAgents/com.insightbridge.dukascopy.fx.bridge.plist"
LOG_DIR="$BASE/reports/dukascopy_bridge"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
cp "$BASE/com.insightbridge.dukascopy.fx.bridge.plist" "$TARGET"
launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/com.insightbridge.dukascopy.fx.bridge"
launchctl kickstart -k "gui/$(id -u)/com.insightbridge.dukascopy.fx.bridge" >/dev/null 2>&1 || true

echo "installed launchagent: $TARGET"
