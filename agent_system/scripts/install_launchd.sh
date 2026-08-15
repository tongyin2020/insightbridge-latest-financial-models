#!/usr/bin/env bash
# Install the Financial Agent System launchd job on macOS.
set -euo pipefail

PLIST="com.insightbridge.financial.agent_system.plist"
PLIST_SRC="$(cd "$(dirname "$0")/.." && pwd)/$PLIST"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"

echo "Installing $PLIST into $LAUNCHD_DIR"
mkdir -p "$LAUNCHD_DIR"
cp "$PLIST_SRC" "$LAUNCHD_DIR/"

# Ensure log dir exists
mkdir -p "${AGENT_BASE:-$HOME/InsightBridge_Financial_Models_Latest}/reports/agent_system"

launchctl unload "$LAUNCHD_DIR/$PLIST" 2>/dev/null || true
launchctl load -w "$LAUNCHD_DIR/$PLIST"

echo "launchd job loaded. It will run every 30 minutes."
echo "Logs: reports/agent_system/launchd_{out,err}.log"
