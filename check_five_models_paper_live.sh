#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO

set -euo pipefail

LABEL="com.insightbridge.five-models.paper"
BASE="$IBREPO"

echo "InsightBridge Five Models Paper Runtime Status"
echo "============================================================"
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | sed -n '1,80p' || echo "launchd service not loaded"
echo "------------------------------------------------------------"
echo "stdout log: $BASE/reports/runtime/launchd_stdout.log"
tail -n 40 "$BASE/reports/runtime/launchd_stdout.log" 2>/dev/null || true
echo "------------------------------------------------------------"
echo "stderr log: $BASE/reports/runtime/launchd_stderr.log"
tail -n 40 "$BASE/reports/runtime/launchd_stderr.log" 2>/dev/null || true
