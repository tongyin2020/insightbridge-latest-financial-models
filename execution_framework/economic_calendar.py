"""
economic_calendar.py
═══════════════════════════════════════════════════════════════════════════════
经济日历 → 自动触发事件。

把"什么时候算重大事件发生"自动化：维护一份事件时间表（UTC），每个事件标注
受影响的品种；到达事件时点（进入触发窗口）时，自动对相关品种调用
pipe.on_event(symbol, event_name, event_time, df)，从而启动"冷静期→确认→下单"闭环。

两种数据来源：
  1. 内置时间表（calendar.json）：你可手工维护，或由外部脚本/连接器写入。
  2. 程序化生成器：对有固定发布规律的事件（CPI/NFP/FOMC/EIA/SOFR 相关）按
     美东时间规则生成近 N 天的预定事件（仍建议用官方日历校正具体日期）。

事件→品种映射（与账户已启用的 7 个品种对齐，不含加密）：
  CPI / FOMC / NFP  -> 影响 MES, MNQ, ZT, ZN, SR3, EURUSD, USDJPY（全市场利率敏感）
  TREASURY_AUCTION  -> 影响 ZT, ZN, SR3
  ECB / BOJ         -> 影响 EURUSD / USDJPY（各自相关）
说明：去掉了 OPEC/EIA（油）与加密相关事件，因为对应品种未启用。

纯标准库。时区换算用固定 UTC 偏移近似；夏令时边界请以官方日历为准。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# 事件 → 受影响品种（仅已启用品种）
EVENT_IMPACT: Dict[str, List[str]] = {
    # BTC 现货对宏观利率事件（CPI/FOMC）敏感，并入 CPI/FOMC 影响面
    "CPI":  ["MES", "MNQ", "ZT", "ZN", "SR3", "EURUSD", "USDJPY", "BTC"],
    "FOMC": ["MES", "MNQ", "ZT", "ZN", "SR3", "EURUSD", "USDJPY", "BTC"],
    "NFP":  ["MES", "MNQ", "ZT", "ZN", "SR3", "EURUSD", "USDJPY"],
    "PPI":  ["MES", "MNQ", "ZT", "ZN", "SR3"],
    "RETAIL_SALES": ["MES", "MNQ", "ZT", "ZN", "USDJPY"],
    "TREASURY_AUCTION": ["ZT", "ZN", "SR3"],
    "ECB":  ["EURUSD"],
    "BOJ":  ["USDJPY"],
}


@dataclass
class CalendarEvent:
    name: str                  # 事件类型，如 "CPI"
    event_time: datetime       # UTC
    symbols: List[str] = field(default_factory=list)
    title: str = ""            # 人类可读
    triggered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "event_time": self.event_time.isoformat(),
                "symbols": self.symbols, "title": self.title,
                "triggered": self.triggered}


class EconomicCalendar:
    """
    用法（接进持续循环）：
        cal = EconomicCalendar(path="reports/runtime/calendar.json",
                               enabled_symbols=ENABLED_SYMBOLS)
        cal.load()                       # 或 cal.generate_default(days=14)
        ...
        due = cal.pop_due(now, window_s=120)   # 进入触发窗口的事件
        for ev in due:
            for sym in ev.symbols:
                df = fetch_1min(sym)
                pipe.on_event(sym, ev.name, ev.event_time, df)
    """

    def __init__(self, path: Optional[str] = None,
                 enabled_symbols: Optional[List[str]] = None):
        self.path = Path(path) if path else None
        self.enabled = set(enabled_symbols or [])
        self.events: List[CalendarEvent] = []

    # ── 加载 / 保存 ───────────────────────────────────────────────────────
    def load(self) -> int:
        if not self.path or not self.path.exists():
            return 0
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.events = []
        for d in data:
            self.events.append(CalendarEvent(
                name=d["name"],
                event_time=datetime.fromisoformat(d["event_time"]),
                symbols=self._filter(d.get("symbols") or EVENT_IMPACT.get(d["name"], [])),
                title=d.get("title", ""), triggered=d.get("triggered", False)))
        return len(self.events)

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([e.to_dict() for e in self.events], ensure_ascii=False, indent=2),
            encoding="utf-8")

    def _filter(self, symbols: List[str]) -> List[str]:
        if not self.enabled:
            return list(symbols)
        return [s for s in symbols if s in self.enabled]

    # ── 手工添加 ──────────────────────────────────────────────────────────
    def add(self, name: str, event_time_utc: datetime,
            symbols: Optional[List[str]] = None, title: str = "") -> None:
        syms = self._filter(symbols or EVENT_IMPACT.get(name.upper(), []))
        if not syms:
            return
        self.events.append(CalendarEvent(name=name.upper(),
                                         event_time=event_time_utc.astimezone(timezone.utc),
                                         symbols=syms, title=title))
        self.events.sort(key=lambda e: e.event_time)

    # ── 到点检测：返回进入触发窗口且未触发过的事件 ────────────────────────
    def pop_due(self, now: datetime, window_s: float = 120.0) -> List[CalendarEvent]:
        now = now.astimezone(timezone.utc)
        due = []
        for ev in self.events:
            if ev.triggered:
                continue
            delta = (now - ev.event_time).total_seconds()
            # 在事件时点之后 0 ~ window_s 内触发一次（避免重复）
            if 0 <= delta <= window_s:
                ev.triggered = True
                due.append(ev)
        if due and self.path:
            self.save()
        return due

    def upcoming(self, now: datetime, horizon_h: float = 24.0) -> List[CalendarEvent]:
        now = now.astimezone(timezone.utc)
        end = now + timedelta(hours=horizon_h)
        return [e for e in self.events
                if not e.triggered and now <= e.event_time <= end]

    # ── 程序化生成（按美东发布规律的近似时间表）────────────────────────────
    def generate_default(self, days: int = 14,
                         start: Optional[datetime] = None) -> int:
        """生成近 days 天的预定事件（近似，UTC）。具体日期请用官方日历校正。
        约定（美东 ET 转 UTC，标准时间 ET=UTC-5，夏令时 ET=UTC-4，此处用 -4 近似）：
          CPI/PPI/Retail/NFP : 08:30 ET = 12:30 UTC
          FOMC 声明          : 14:00 ET = 18:00 UTC
          国债拍卖           : 13:00 ET = 17:00 UTC
        生成规则（近似）：
          - NFP：每月第一个周五
          - CPI：每月 ~10–13 号工作日（这里取每月 12 号工作日近似）
          - FOMC：每约 6 周一次（用 8 周规律近似，建议手工覆盖准确日）
          - 国债拍卖：每周二/周三 17:00 UTC（2Y/10Y 近似）
        """
        start = (start or datetime.now(timezone.utc)).astimezone(timezone.utc)
        added = 0
        for d in range(days):
            day = (start + timedelta(days=d)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            wd = day.weekday()  # 0=Mon
            # NFP：每月第一个周五
            if wd == 4 and 1 <= day.day <= 7:
                self.add("NFP", day.replace(hour=12, minute=30),
                         title="Nonfarm Payrolls"); added += 1
            # CPI：每月 12 号附近的工作日
            if day.day == 12 and wd < 5:
                self.add("CPI", day.replace(hour=12, minute=30),
                         title="CPI"); added += 1
            # 国债拍卖：周二/周三
            if wd in (1, 2):
                self.add("TREASURY_AUCTION", day.replace(hour=17, minute=0),
                         title="UST Auction"); added += 1
        # 注意：FOMC/ECB/BOJ 日期不规则，建议用 add() 手工加准确时点。
        if self.path:
            self.save()
        return added
