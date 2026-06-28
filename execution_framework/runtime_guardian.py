"""
runtime_guardian.py
═══════════════════════════════════════════════════════════════════════════════
持续运行守护：心跳 (heartbeat) + 死手开关 (dead-man's switch)。

目标：让系统能长期无人值守跑模拟盘，并在异常时自我保护。
  1. 心跳：主循环每次迭代写一次心跳文件（时间戳 + 状态快照）。
  2. 死手开关：独立看门狗线程检测心跳是否超时（默认 90s）。
     超时 = 主循环卡死/崩溃 → 触发紧急处置：
        - 调用 on_dead 回调（通常：撤掉所有未结单 + 管线 halt + 外部告警）
  3. 连接健康：定期检查 IB 连接，断开则触发会话重连。
  4. 可选外部告警：Telegram（环境变量），失败静默不影响主流程。

纯标准库 + 可选 requests（Telegram）。看门狗用 threading，不阻塞主循环。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import urllib.request


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _epoch() -> float:
    return time.time()


class RuntimeGuardian:
    """
    用法：
        g = RuntimeGuardian(heartbeat_path="reports/runtime/hb.json",
                            timeout_s=90,
                            on_dead=lambda why: (session.cancel_all(), pipe.halt(why)))
        g.start()
        while running:
            ... 主循环 ...
            g.beat({"symbols_scanned": 7, "halted": pipe.is_halted})
        g.stop()
    """

    def __init__(self, heartbeat_path: str,
                 timeout_s: float = 90.0,
                 check_interval_s: float = 15.0,
                 on_dead: Optional[Callable[[str], None]] = None,
                 health_check: Optional[Callable[[], bool]] = None,
                 on_unhealthy: Optional[Callable[[], None]] = None,
                 telegram: bool = False):
        self.heartbeat_path = Path(heartbeat_path)
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s
        self.check_interval_s = check_interval_s
        self.on_dead = on_dead
        self.health_check = health_check
        self.on_unhealthy = on_unhealthy
        self.telegram = telegram

        self._last_beat = _epoch()
        self._running = False
        self._dead_fired = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ── 心跳 ──────────────────────────────────────────────────────────────
    def beat(self, status: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._last_beat = _epoch()
        payload = {"ts": _utcnow(), "epoch": self._last_beat,
                   "pid": os.getpid(), "status": status or {}}
        try:
            tmp = self.heartbeat_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.heartbeat_path)   # 原子替换
        except Exception:   # noqa: BLE001
            pass

    # ── 看门狗线程 ────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._dead_fired = False
        self._last_beat = _epoch()
        self._thread = threading.Thread(target=self._watch, daemon=True,
                                        name="dead-man-switch")
        self._thread.start()
        self.notify("RuntimeGuardian 启动", f"timeout={self.timeout_s}s")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _watch(self) -> None:
        while self._running:
            time.sleep(self.check_interval_s)
            if not self._running:
                break

            # 1) 心跳超时检测（死手开关）
            with self._lock:
                age = _epoch() - self._last_beat
            if age > self.timeout_s and not self._dead_fired:
                self._dead_fired = True
                why = f"heartbeat_timeout_{age:.0f}s"
                self.notify("⛔ 死手开关触发", why)
                if self.on_dead:
                    try:
                        self.on_dead(why)
                    except Exception as exc:   # noqa: BLE001
                        self.notify("on_dead 执行异常", str(exc))

            # 2) 连接健康检查
            if self.health_check is not None:
                try:
                    healthy = bool(self.health_check())
                except Exception:   # noqa: BLE001
                    healthy = False
                if not healthy and self.on_unhealthy:
                    try:
                        self.on_unhealthy()
                    except Exception:   # noqa: BLE001
                        pass

    @property
    def is_dead(self) -> bool:
        return self._dead_fired

    # ── 外部告警（可选 Telegram）──────────────────────────────────────────
    def notify(self, title: str, body: str = "") -> None:
        msg = f"[{_utcnow()}] {title} {body}".strip()
        try:
            print(msg)
        except Exception:   # noqa: BLE001
            pass
        if not self.telegram:
            return
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat:
            return
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = json.dumps({"chat_id": chat, "text": msg}).encode("utf-8")
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)   # noqa: S310
        except Exception:   # noqa: BLE001
            pass   # 告警失败不得影响主流程


# ── 独立巡检：外部进程读取心跳文件判断主进程是否存活 ─────────────────────────
def check_heartbeat(heartbeat_path: str, timeout_s: float = 90.0) -> Dict[str, Any]:
    """供外部 cron / 监控脚本调用，判断主进程是否仍在心跳。"""
    p = Path(heartbeat_path)
    if not p.exists():
        return {"alive": False, "reason": "no_heartbeat_file"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:   # noqa: BLE001
        return {"alive": False, "reason": f"unreadable:{exc}"}
    age = _epoch() - float(data.get("epoch", 0))
    return {"alive": age <= timeout_s, "age_s": round(age, 1),
            "last_status": data.get("status", {}), "pid": data.get("pid")}
