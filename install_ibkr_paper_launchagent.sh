#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
TARGET="$HOME/Library/LaunchAgents/com.insightbridge.ibkr.paper.gateway.plist"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

"$PY" "$BASE/prepare_ibkr_paper_runtime.py" >/dev/null
mkdir -p "$HOME/Library/LaunchAgents" "$BASE/ibkr_runtime/logs"
cp "$BASE/com.insightbridge.ibkr.paper.gateway.plist" "$TARGET"
launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/com.insightbridge.ibkr.paper.gateway"

echo "installed launchagent: $TARGET"
