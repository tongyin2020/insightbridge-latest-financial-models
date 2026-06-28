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
  ✅ EURUSD (现货外汇, IDEALPRO)
  ✅ USDJPY (现货外汇, IDEALPRO)
  ❌ MBT   (Micro Bitcoin) —— 当前账户【无加密货币交易权限】，默认禁用。
            等开通权限后，把 "MBT" 加入 ENABLED_SYMBOLS 即可。

运行入口默认只交易 ENABLED_SYMBOLS 里的品种。
"""

from __future__ import annotations

from typing import List

# 当前启用（7 个，不含加密）
ENABLED_SYMBOLS: List[str] = [
    "MES", "MNQ",        # 股指
    "ZT", "ZN",          # 国债
    "SR3",               # 利率
    "EURUSD", "USDJPY",  # 外汇
]

# 已实现但因权限/选择暂不启用
DISABLED_SYMBOLS: List[str] = [
    "MBT",               # 无加密货币权限
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
    "MBT": "Micro Bitcoin (CME) — 无权限，默认禁用",
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
