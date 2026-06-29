#!/bin/zsh

set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
LABEL="com.insightbridge.five-models.paper"
PLIST="$BASE/com.insightbridge.five-models.paper.plist"
GUI_DOMAIN="gui/$(id -u)"

echo "InsightBridge Five Models Recovery After IBKR Re-Login"
echo "============================================================"
echo "Step 1/4: checking TWS paper channel..."

if ! "$PY" "$BASE/check_tws_paper_channel.py"; then
  echo
  echo "TWS paper channel is still not ready."
  echo "Please make sure:"
  echo "1. TWS paper account is logged in"
  echo "2. API is enabled"
  echo "3. Port 7497 is open"
  exit 1
fi

echo
echo "Step 2/4: restarting five-model launchd service..."
launchctl bootout "$GUI_DOMAIN" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST"
launchctl enable "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1 || true

echo
echo "Step 3/4: waiting for heartbeat..."
sleep 5

echo
echo "Step 4/4: verifying runtime health..."
"$PY" "$BASE/check_five_models_runtime_health.py"

echo
echo "Recovery complete."
echo "If service_running=True and heartbeat_fresh=True, the five paper-trading models are back online."
