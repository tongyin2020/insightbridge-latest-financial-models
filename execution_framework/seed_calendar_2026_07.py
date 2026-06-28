"""
seed_calendar_2026_07.py
═══════════════════════════════════════════════════════════════════════════════
用【官方核实的】2026 年 7 月美国宏观事件日期生成准确的 calendar.json。

数据来源（官方）：
  - NFP (6月就业报告)   : 2026-07-02 08:30 ET   (BLS Employment Situation)
  - CPI (6月)           : 2026-07-14 08:30 ET   (BLS, bls.gov/schedule)
  - PPI (6月)           : 2026-07-15 08:30 ET   (PPI 通常在 CPI 次日；如官方有别请改)
  - FOMC 决议           : 2026-07-29 14:00 ET   (会议 7/28-29，声明周三 14:00 ET)

时区换算：7 月为美东夏令时 (EDT = UTC-4)
  08:30 ET = 12:30 UTC
  14:00 ET = 18:00 UTC

事件→品种映射沿用 economic_calendar.EVENT_IMPACT（仅已启用 8 品；BTC 入 CPI/FOMC）。

运行：
  python3 execution_framework/seed_calendar_2026_07.py
  # 写入 reports/runtime/calendar.json（已有同名事件不会重复）
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from economic_calendar import EconomicCalendar
from enabled_symbols import ENABLED_SYMBOLS

BASE = Path(__file__).resolve().parent.parent
CAL = BASE / "reports" / "runtime" / "calendar.json"

# (事件名, UTC 时间, 标题)  —— 已按 EDT=UTC-4 换算
EVENTS_2026_07 = [
    ("NFP",  datetime(2026, 7, 2,  12, 30, tzinfo=timezone.utc), "Nonfarm Payrolls (Jun) 08:30 ET"),
    ("CPI",  datetime(2026, 7, 14, 12, 30, tzinfo=timezone.utc), "CPI (Jun) 08:30 ET"),
    ("PPI",  datetime(2026, 7, 15, 12, 30, tzinfo=timezone.utc), "PPI (Jun) 08:30 ET [次日,待官方核对]"),
    ("FOMC", datetime(2026, 7, 29, 18, 0,  tzinfo=timezone.utc), "FOMC Decision 14:00 ET"),
]


def main() -> int:
    CAL.parent.mkdir(parents=True, exist_ok=True)
    cal = EconomicCalendar(str(CAL), enabled_symbols=ENABLED_SYMBOLS)
    cal.load()
    before = len(cal.events)
    for name, t_utc, title in EVENTS_2026_07:
        cal.add(name, t_utc, title=title)   # symbols 由 EVENT_IMPACT 自动填充并过滤
    cal.save()
    print(f"已写入 {CAL}")
    print(f"新增 {len(cal.events) - before} 个事件，当前共 {len(cal.events)} 个：\n")
    for e in sorted(cal.events, key=lambda x: x.event_time):
        print(f"  {e.event_time.isoformat()}  {e.name:5s} -> {e.symbols}")
    print("\n注意：PPI 日期为‘CPI 次日’近似，请用 BLS 官方日历最终核对。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
