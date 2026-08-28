"""
enabled_symbols.py
═══════════════════════════════════════════════════════════════════════════════
启用品种清单 —— 与盈透(IBKR)模拟账户的实际交易权限对齐。

用户当前模拟账户权限：
  ✅ MES   (Micro E-mini S&P 500, CME)
  ✅ MNQ   (Micro E-mini Nasdaq-100, CME)
  ✅ ZT    (2-Year US T-Note, CBOT)
  ✅ ZN    (10-Year US T-Note, CBOT)
  ✅ SR3   (3-Month SOFR, CME)
  ✅ EURUSD/USDJPY/AUDUSD/NZDUSD/GBPUSD/AUDJPY/NZDJPY (现货外汇, IDEALPRO)
  ❌ MBT   (Micro Bitcoin) —— 当前账户【无加密货币交易权限】，默认禁用。
            等开通权限后，把 "MBT" 加入 ENABLED_SYMBOLS 即可。
  ✅ CL    (WTI 原油, NYMEX) —— 入场规则已就绪（DEFAULT_RULES，④号产品），
            用户已确认账户具备 NYMEX 权限（2026-08-28），默认启用。

运行入口默认只交易 ENABLED_SYMBOLS 里的品种。
"""

from __future__ import annotations

from typing import List

# 当前启用（16 个）
ENABLED_SYMBOLS: List[str] = [
    "MES", "MNQ",        # 股指
    "ZT", "ZN",          # 国债
    "SR3",               # 利率
    "CL",                # 商品（WTI 原油，NYMEX）
    "EURUSD", "USDJPY", "AUDUSD", "NZDUSD", "GBPUSD", "AUDJPY", "NZDJPY",  # 外汇
    "BTC", "ETH", "SOL",  # 现货加密（ZEROHASH），软止损
]

# 已实现但因选择暂不启用
DISABLED_SYMBOLS: List[str] = [
    "MBT",               # CME 微型比特币期货（现用现货 BTC代替）
]

# 备注：用于日志/报告展示
SYMBOL_NOTES = {
    "MES": "Micro E-mini S&P 500 (CME)",
    "MNQ": "Micro E-mini Nasdaq-100 (CME)",
    "ZT": "2Y T-Note (CBOT)",
    "ZN": "10Y T-Note (CBOT)",
    "SR3": "3M SOFR (CME)",
    "EURUSD": "EUR/USD spot (IDEALPRO)",
    "USDJPY": "USD/JPY spot (IDEALPRO)",
    "AUDUSD": "AUD/USD spot (IDEALPRO) — ③号外汇模型扩展，2026-08-28 接线",
    "NZDUSD": "NZD/USD spot (IDEALPRO) — ③号外汇模型扩展，2026-08-28 接线",
    "GBPUSD": "GBP/USD spot (IDEALPRO) — ③号外汇模型扩展，2026-08-28 接线",
    "AUDJPY": "AUD/JPY spot (IDEALPRO) — ③号外汇模型扩展，2026-08-28 接线",
    "NZDJPY": "NZD/JPY spot (IDEALPRO) — ③号外汇模型扩展，2026-08-28 接线",
    "BTC": "BTC/USD 现货 (ZEROHASH) — IOC 限价 + 软止损",
    "ETH": "ETH/USD 现货 (ZEROHASH) — IOC 限价 + 软止损（tick 需核实）",
    "SOL": "SOL/USD 现货 (ZEROHASH) — IOC 限价 + 软止损（tick 需核实）",
    "MBT": "Micro Bitcoin 期货 (CME) — 现用现货 BTC 代替，默认禁用",
    "CL": "WTI 原油期货 (NYMEX) — 规则已就绪，NYMEX 权限已确认（2026-08-28），默认启用",
}


def filter_enabled(symbols: List[str]) -> List[str]:
    """从请求的品种里只保留已启用的，过滤掉无权限/禁用品种，并去重保序。"""
    seen = set()
    out = []
    for s in symbols:
        su = s.strip().upper().replace("/", "")
        if su in ENABLED_SYMBOLS and su not in seen:
            out.append(su)
            seen.add(su)
    return out


def rejected(symbols: List[str]) -> List[str]:
    """返回请求里被拒绝（禁用/无权限/未知）的品种，便于提示用户。"""
    out = []
    for s in symbols:
        su = s.strip().upper().replace("/", "")
        if su not in ENABLED_SYMBOLS:
            out.append(su)
    return out
