#!/bin/zsh

set -euo pipefail

LABEL="com.insightbridge.five-models.paper"
BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"

echo "InsightBridge Five Models Paper Runtime Status"
echo "============================================================"
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | sed -n '1,80p' || echo "launchd service not loaded"
echo "------------------------------------------------------------"
echo "stdout log: $BASE/reports/runtime/launchd_stdout.log"
tail -n 40 "$BASE/reports/runtime/launchd_stdout.log" 2>/dev/null || true
echo "------------------------------------------------------------"
echo "stderr log: $BASE/reports/runtime/launchd_stderr.log"
tail -n 40 "$BASE/reports/runtime/launchd_stderr.log" 2>/dev/null || true
