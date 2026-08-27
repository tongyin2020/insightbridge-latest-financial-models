#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
TARGET="$HOME/Library/LaunchAgents/com.insightbridge.ibkr.paper.gateway.plist"
SUPPORT_DIR="$HOME/Library/InsightBridge_IBKR"
WRAPPER="$SUPPORT_DIR/ensure_ib_gateway_launchd.sh"
SUPPORT_RUNTIME="$SUPPORT_DIR/runtime"
SUPPORT_PRIVATE="$SUPPORT_RUNTIME/private"
SUPPORT_SETTINGS="$SUPPORT_RUNTIME/ib_settings/paper"
SUPPORT_LOGS="$SUPPORT_RUNTIME/logs"
SUPPORT_IBC_ROOT="$SUPPORT_DIR/IBC/resources"
SUPPORT_CONFIG="$SUPPORT_PRIVATE/config.paper.ini"
SUPPORT_GUI_COMMAND="$SUPPORT_RUNTIME/run_ibkr_gateway_gui.command"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

"$PY" "$BASE/prepare_ibkr_paper_runtime.py" >/dev/null
mkdir -p \
  "$HOME/Library/LaunchAgents" \
  "$BASE/ibkr_runtime/logs" \
  "$SUPPORT_DIR" \
  "$SUPPORT_PRIVATE" \
  "$SUPPORT_SETTINGS" \
  "$SUPPORT_LOGS"

rm -rf "$SUPPORT_IBC_ROOT"
mkdir -p "$(dirname "$SUPPORT_IBC_ROOT")"
cp -R "$BASE/third_party/IBC/resources" "$SUPPORT_IBC_ROOT"

cp "$BASE/ibkr_runtime/private/config.paper.ini" "$SUPPORT_CONFIG"
/usr/bin/perl -0pi -e 's{\Q'"$IBREPO"'/ibkr_runtime/ib_settings/paper\E}{'"$SUPPORT_SETTINGS"'}g' "$SUPPORT_CONFIG"

cat > "$WRAPPER" <<EOF
#!/bin/zsh
set -euo pipefail

BASE="$BASE"
PY="$PY"
SUPPORT_DIR="$SUPPORT_DIR"
SUPPORT_RUNTIME="$SUPPORT_RUNTIME"
SUPPORT_PRIVATE="$SUPPORT_PRIVATE"
SUPPORT_SETTINGS="$SUPPORT_SETTINGS"
SUPPORT_LOGS="$SUPPORT_LOGS"
SUPPORT_IBC_ROOT="$SUPPORT_IBC_ROOT"
SUPPORT_CONFIG="$SUPPORT_CONFIG"
SUPPORT_GUI_COMMAND="$SUPPORT_GUI_COMMAND"
APP_DIR="/Users/tongyin/Applications"
LAUNCH_LOG="\$SUPPORT_LOGS/ib_gateway_launch.log"
GUI_LOG="\$SUPPORT_LOGS/ib_gateway_gui_launch.log"
WATCHDOG_STATE="\$SUPPORT_RUNTIME/watchdog_state.json"
API_PORT=4002
LABEL_FIVE="com.insightbridge.five-models.paper"
FIVE_PLIST="/Users/tongyin/Library/LaunchAgents/com.insightbridge.five-models.paper.plist"
PAPER_CHECK="$BASE/check_ibkr_paper_setup.py"

now_epoch() {
  date +%s
}

resolve_gateway_version() {
  local latest
  latest="\$(find "\$APP_DIR" -maxdepth 1 -type d -name 'IB Gateway 10.*' 2>/dev/null | sort -V | tail -n 1)"
  if [[ -z "\$latest" ]]; then
    return 1
  fi
  basename "\$latest" | sed 's/^IB Gateway //'
}

port_live() {
  /usr/bin/nc -z 127.0.0.1 "\$API_PORT" >/dev/null 2>&1
}

gateway_ready() {
  if ! port_live; then
    return 1
  fi
  local payload
  payload="\$("\$PY" "\$PAPER_CHECK" --json --port "\$API_PORT" 2>/dev/null || true)"
  if [[ -z "\$payload" ]]; then
    return 1
  fi
  "\$PY" - <<'PY' <<< "\$payload"
import json
import sys
try:
    payload = json.loads(sys.stdin.read())
except Exception:
    raise SystemExit(1)
ok = bool(((payload.get("checks") or {}).get("read_only_connection") or {}).get("ok"))
raise SystemExit(0 if ok else 1)
PY
}

write_state() {
  local state_name="\$1"
  local note="\$2"
  cat > "\$WATCHDOG_STATE" <<JSON
{
  "updated_at": "\$(date '+%Y-%m-%d %H:%M:%S')",
  "status": "\$state_name",
  "note": "\$note"
}
JSON
}

recover_five_models() {
  if [[ ! -f "\$FIVE_PLIST" ]]; then
    return 0
  fi
  launchctl enable "gui/\$(id -u)/\$LABEL_FIVE" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/\$(id -u)/\$LABEL_FIVE" >/dev/null 2>&1 || true
}

if gateway_ready; then
  recover_five_models
  write_state "live" "API port and read-only handshake already reachable."
  exit 0
fi

GATEWAY_VERSION="\$(resolve_gateway_version || true)"
if [[ -z "\$GATEWAY_VERSION" ]]; then
  write_state "attention" "No IB Gateway 10.x installation found."
  exit 1
fi

nohup "\$SUPPORT_IBC_ROOT/scripts/ibcstart.sh" \
  "\$GATEWAY_VERSION" \
  --gateway \
  --tws-path="\$APP_DIR" \
  --tws-settings-path="\$SUPPORT_SETTINGS" \
  --ibc-path="\$SUPPORT_IBC_ROOT" \
  --ibc-ini="\$SUPPORT_CONFIG" \
  --mode=paper \
  --on2fatimeout=restart \
  >"\$LAUNCH_LOG" 2>&1 &

sleep 10

if gateway_ready; then
  recover_five_models
  write_state "live" "Background IBC launch restored API and handshake."
  exit 0
fi

cat > "\$GUI_LOG" <<LOG
launched_at=\$(date '+%Y-%m-%d %H:%M:%S')
launcher=gui_terminal
gateway_version=\$GATEWAY_VERSION
LOG

cat > "\$SUPPORT_GUI_COMMAND" <<CMD
#!/bin/bash
export TWS_MAJOR_VRSN="\$GATEWAY_VERSION"
export IBC_INI="\$SUPPORT_CONFIG"
export TRADING_MODE="paper"
export TWOFA_TIMEOUT_ACTION="restart"
export IBC_PATH="\$SUPPORT_IBC_ROOT"
export TWS_PATH="\$APP_DIR"
export TWS_SETTINGS_PATH="\$SUPPORT_SETTINGS"
export LOG_PATH="\$SUPPORT_LOGS"
export JAVA_PATH=""
export APP="GATEWAY"
bash "\$SUPPORT_IBC_ROOT/scripts/displaybannerandlaunch.sh" >> "\$GUI_LOG" 2>&1
CMD

chmod +x "\$SUPPORT_GUI_COMMAND"
/usr/bin/osascript <<OSA
tell application "Terminal"
  activate
  do script "bash \$SUPPORT_GUI_COMMAND"
end tell
OSA

sleep 18

if gateway_ready; then
  recover_five_models
  write_state "live" "GUI IBC launch restored API and handshake."
  exit 0
fi

write_state "attention" "API or read-only handshake still unavailable after background and GUI recovery."
exit 1
EOF

chmod +x "$WRAPPER"

cp "$BASE/com.insightbridge.ibkr.paper.gateway.plist" "$TARGET"
launchctl bootout "gui/$(id -u)" "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/com.insightbridge.ibkr.paper.gateway"
launchctl kickstart -k "gui/$(id -u)/com.insightbridge.ibkr.paper.gateway" >/dev/null 2>&1 || true

echo "installed launchagent: $TARGET"
echo "wrapper: $WRAPPER"
