#!/bin/bash
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
IBC_ROOT="$BASE/third_party/IBC/resources"
DISPLAY_AND_LAUNCH="$IBC_ROOT/scripts/displaybannerandlaunch.sh"
RUNTIME_DIR="$BASE/ibkr_runtime"
LOG_DIR="$RUNTIME_DIR/logs"
GUI_LAUNCH_LOG="$LOG_DIR/ib_gateway_gui_launch.log"
GUI_COMMAND_FILE="$RUNTIME_DIR/run_ibkr_gateway_gui.command"
APPLICATIONS_DIR="/Users/tongyin/Applications"

resolve_gateway_version() {
  if [[ -n "${IB_GATEWAY_VERSION:-}" ]]; then
    echo "${IB_GATEWAY_VERSION}"
    return 0
  fi

  local latest
  latest="$(
    find "$APPLICATIONS_DIR" -maxdepth 1 -type d -name 'IB Gateway 10.*' 2>/dev/null \
      | sort -V \
      | tail -n 1
  )"

  if [[ -z "$latest" ]]; then
    return 1
  fi

  basename "$latest" | sed 's/^IB Gateway //'
}

"$PY" "$BASE/prepare_ibkr_paper_runtime.py" >/dev/null
mkdir -p "$LOG_DIR"

if ! GATEWAY_VERSION="$(resolve_gateway_version)"; then
  echo "No installed IB Gateway 10.x folder found under $APPLICATIONS_DIR"
  exit 1
fi

if [[ ! -f "$DISPLAY_AND_LAUNCH" ]]; then
  echo "Missing IBC display/launch script: $DISPLAY_AND_LAUNCH"
  exit 1
fi

cat > "$GUI_LAUNCH_LOG" <<EOF
launched_at=$(date '+%Y-%m-%d %H:%M:%S')
launcher=gui_terminal
gateway_version=$GATEWAY_VERSION
EOF

cat > "$GUI_COMMAND_FILE" <<EOF
#!/bin/bash
export TWS_MAJOR_VRSN="$GATEWAY_VERSION"
export IBC_INI="$RUNTIME_DIR/private/config.paper.ini"
export TRADING_MODE="paper"
export TWOFA_TIMEOUT_ACTION="restart"
export IBC_PATH="$IBC_ROOT"
export TWS_PATH="$APPLICATIONS_DIR"
export TWS_SETTINGS_PATH="$RUNTIME_DIR/ib_settings/paper"
export LOG_PATH="$LOG_DIR"
export JAVA_PATH=""
export APP="GATEWAY"
bash "$DISPLAY_AND_LAUNCH" >> "$GUI_LAUNCH_LOG" 2>&1
EOF

chmod +x "$GUI_COMMAND_FILE"

/usr/bin/osascript <<EOF
tell application "Terminal"
  activate
  do script "bash $GUI_COMMAND_FILE"
end tell
EOF

echo "IB Gateway GUI launcher triggered."
echo "gateway_version: $GATEWAY_VERSION"
echo "terminal_log: $GUI_LAUNCH_LOG"
echo "terminal_command: $GUI_COMMAND_FILE"
