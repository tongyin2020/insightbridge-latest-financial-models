#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="/opt/anaconda3/bin/python3"
SUPPORT_DIR="/Users/tongyin/Library/InsightBridge_IBKR"
SUPPORT_RUNTIME="/Users/tongyin/Library/InsightBridge_IBKR/runtime"
SUPPORT_PRIVATE="/Users/tongyin/Library/InsightBridge_IBKR/runtime/private"
SUPPORT_SETTINGS="/Users/tongyin/Library/InsightBridge_IBKR/runtime/ib_settings/paper"
SUPPORT_LOGS="/Users/tongyin/Library/InsightBridge_IBKR/runtime/logs"
SUPPORT_IBC_ROOT="/Users/tongyin/Library/InsightBridge_IBKR/IBC/resources"
SUPPORT_CONFIG="/Users/tongyin/Library/InsightBridge_IBKR/runtime/private/config.paper.ini"
SUPPORT_GUI_COMMAND="/Users/tongyin/Library/InsightBridge_IBKR/runtime/run_ibkr_gateway_gui.command"
APP_DIR="/Users/tongyin/Applications"
LAUNCH_LOG="$SUPPORT_LOGS/ib_gateway_launch.log"
GUI_LOG="$SUPPORT_LOGS/ib_gateway_gui_launch.log"
WATCHDOG_STATE="$SUPPORT_RUNTIME/watchdog_state.json"
API_PORT=4002
LABEL_FIVE="com.insightbridge.five-models.paper"
FIVE_PLIST="/Users/tongyin/Library/LaunchAgents/com.insightbridge.five-models.paper.plist"
PAPER_CHECK="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_ibkr_paper_setup.py"

now_epoch() {
  date +%s
}

resolve_gateway_version() {
  local latest
  latest="$(find "$APP_DIR" -maxdepth 1 -type d -name 'IB Gateway 10.*' 2>/dev/null | sort -V | tail -n 1)"
  if [[ -z "$latest" ]]; then
    return 1
  fi
  basename "$latest" | sed 's/^IB Gateway //'
}

port_live() {
  /usr/bin/nc -z 127.0.0.1 "$API_PORT" >/dev/null 2>&1
}

gateway_ready() {
  if ! port_live; then
    return 1
  fi
  local payload
  payload="$("$PY" "$PAPER_CHECK" --json --port "$API_PORT" 2>/dev/null || true)"
  if [[ -z "$payload" ]]; then
    return 1
  fi
  # 用管道把 payload 传给 python 判断只读握手是否成功。
  # (原实现同时用 heredoc 当脚本 + herestring 当 stdin，二者冲突导致永远判 false，
  #  从而让旧版守护误以为 Gateway 一直没登录 → 不停自动登录/误报，这里修正。)
  printf '%s' "$payload" | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
ok = bool(((d.get("checks") or {}).get("read_only_connection") or {}).get("ok"))
sys.exit(0 if ok else 1)
'
}

write_state() {
  local state_name="$1"
  local note="$2"
  cat > "$WATCHDOG_STATE" <<JSON
{
  "updated_at": "$(date '+%Y-%m-%d %H:%M:%S')",
  "status": "$state_name",
  "note": "$note"
}
JSON
}

recover_five_models() {
  # 只在必要时动五模型，避免每次巡检(每180s)都重启它造成抖动：
  #   - 进程不存在 → 拉起
  #   - 进程在跑但被死手开关 halted=true → 强制重启以解除 halted
  #   - 进程在跑且正常 → 不动
  if [[ ! -f "$FIVE_PLIST" ]]; then
    return 0
  fi
  launchctl enable "gui/$(id -u)/$LABEL_FIVE" >/dev/null 2>&1 || true
  local hb="$BASE/reports/runtime/heartbeat.json"
  if ! pgrep -f "run_tws_continuous.py" >/dev/null 2>&1; then
    launchctl kickstart "gui/$(id -u)/$LABEL_FIVE" >/dev/null 2>&1 || true
    return 0
  fi
  if "$PY" -c "import json,sys; d=json.load(open('$hb')); sys.exit(0 if d.get('status',{}).get('halted') else 1)" 2>/dev/null; then
    launchctl kickstart -k "gui/$(id -u)/$LABEL_FIVE" >/dev/null 2>&1 || true
  fi
}

if gateway_ready; then
  recover_five_models
  write_state "live" "API port and read-only handshake already reachable."
  exit 0
fi

# 按用户要求：仅监控 + 断线提醒，绝不自动登录 IB Gateway（2FA 需用户手动完成）。
# 若 4002 不可达 / 只读握手失败：记录状态 + 弹出系统通知提醒用户手动登录，然后退出。
NOTE="IB Gateway 未登录或 API(4002) 不可达，请手动登录 IB Gateway。（已按您的要求关闭自动登录）"
write_state "attention" "$NOTE"
/usr/bin/osascript -e "display notification \"$NOTE\" with title \"InsightBridge IBKR 守护\" sound name \"Basso\"" >/dev/null 2>&1 || true
# 返回 0：这是"仅监控"模式，未登录属预期内的等待状态，不应让 launchd 视为失败。
exit 0
