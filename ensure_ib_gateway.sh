#!/bin/zsh
IBREPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export IBREPO
set -euo pipefail

BASE="$IBREPO"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
STATE_DIR="$BASE/ibkr_runtime"
STATE_FILE="$STATE_DIR/watchdog_state.json"
RUNTIME_CHECK="$BASE/check_ibkr_gateway_runtime.py"
START_BG="$BASE/start_ibkr_paper_gateway.sh"
START_GUI="$BASE/start_ibkr_paper_gateway_gui.sh"
RECOVER_MODELS="$BASE/recover_five_models_after_ibkr_relogin.sh"
FIVE_MODELS_HEALTH="$BASE/check_five_models_runtime_health.py"
GUI_COOLDOWN_SEC=180

mkdir -p "$STATE_DIR"

now_epoch() {
  date +%s
}

read_state_value() {
  local key="$1"
  if [[ ! -f "$STATE_FILE" ]]; then
    return 1
  fi
  "$PY" - "$STATE_FILE" "$key" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
try:
    payload = json.loads(path.read_text())
except Exception:
    raise SystemExit(1)
value = payload.get(key, "")
if value is None:
    value = ""
print(value)
PY
}

write_state() {
  local gateway_status="$1"
  local last_gui_launch_at="$2"
  local note="$3"
  "$PY" - "$STATE_FILE" "$gateway_status" "$last_gui_launch_at" "$note" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

path = Path(sys.argv[1])
payload = {}
if path.exists():
    try:
        payload = json.loads(path.read_text())
    except Exception:
        payload = {}
payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
payload["gateway_status"] = sys.argv[2]
payload["last_gui_launch_at_epoch"] = int(sys.argv[3]) if sys.argv[3] else 0
payload["note"] = sys.argv[4]
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
PY
}

gateway_live() {
  local output
  output="$("$PY" "$RUNTIME_CHECK" 2>/dev/null || true)"
  if [[ "$output" == *"Overall: LIVE"* ]]; then
    return 0
  fi
  return 1
}

five_models_live() {
  local output
  output="$("$PY" "$FIVE_MODELS_HEALTH" 2>/dev/null || true)"
  if [[ "$output" == *"Overall: LIVE"* ]]; then
    return 0
  fi
  return 1
}

ensure_gateway() {
  if gateway_live; then
    return 0
  fi

  bash "$START_BG" >/dev/null 2>&1 || true
  sleep 8
  if gateway_live; then
    return 0
  fi

  local last_gui_launch_at=0
  last_gui_launch_at="$(read_state_value "last_gui_launch_at_epoch" 2>/dev/null || echo 0)"
  local now
  now="$(now_epoch)"
  local delta=$(( now - ${last_gui_launch_at:-0} ))

  if (( delta >= GUI_COOLDOWN_SEC )); then
    bash "$START_GUI" >/dev/null 2>&1 || true
    write_state "gui_launch_requested" "$now" "Triggered GUI launcher because API was not live."
    sleep 18
  fi

  if gateway_live; then
    return 0
  fi
  return 1
}

main() {
  if ensure_gateway; then
    local last_gui
    last_gui="$(read_state_value "last_gui_launch_at_epoch" 2>/dev/null || echo 0)"
    write_state "live" "${last_gui:-0}" "Gateway API live."
    if ! five_models_live; then
      bash "$RECOVER_MODELS" >/dev/null 2>&1 || true
    fi
    echo "IB Gateway watchdog: LIVE"
    return 0
  fi

  local last_gui
  last_gui="$(read_state_value "last_gui_launch_at_epoch" 2>/dev/null || echo 0)"
  write_state "attention" "${last_gui:-0}" "Gateway API still not live after recovery attempts."
  echo "IB Gateway watchdog: ATTENTION"
  return 1
}

main "$@"
