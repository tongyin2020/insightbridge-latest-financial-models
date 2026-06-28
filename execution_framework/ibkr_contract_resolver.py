"""
ibkr_contract_resolver.py
═══════════════════════════════════════════════════════════════════════════════
IBKR 合约解析器：保证下单合约"唯一可解析"。

为什么需要这个：
  - IBKR 官方说明，连续期货 (CONTFUT) 主要用于历史/行情数据请求，**不能直接用于下单**。
  - 真实/模拟下单时，合约对象必须足够具体，否则 IBKR 会返回 ambiguity（错误码 200）。
  - 正确做法：reqContractDetails(模糊模板) -> 在返回的多个到期月中选近月/主力
    -> 锁定 conId -> 用 conId 下单，并缓存结果。

本模块同时提供 ibapi（同步 EClient/EWrapper）与 ib_insync 两种用法的解析逻辑骨架。
默认实现基于 ib_insync（项目其余部分使用 ib_insync）。若无 ib_insync，提供纯模板回退。

注意：本模块只负责"解析与锁定合约"，不下单。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ── FX 现货：直接可解析，无需到期月 ──────────────────────────────────────────
FX_SPECS: Dict[str, Dict[str, str]] = {
    "EURUSD": {"symbol": "EUR", "currency": "USD", "exchange": "IDEALPRO"},
    "USDJPY": {"symbol": "USD", "currency": "JPY", "exchange": "IDEALPRO"},
}

# ── 期货：模糊模板，交给 reqContractDetails 展开到期月 ───────────────────────
CRYPTO_SPECS: Dict[str, Dict[str, str]] = {
    "BTC": {"symbol": "BTC", "currency": "USD", "exchange": "PAXOS"},
    # 如需 ETH: "ETH": {"symbol": "ETH", "currency": "USD", "exchange": "PAXOS"},
}

FUT_SPECS: Dict[str, Dict[str, str]] = {
    "MES": {"symbol": "MES", "exchange": "CME", "currency": "USD"},
    "MNQ": {"symbol": "MNQ", "exchange": "CME", "currency": "USD"},
    "MBT": {"symbol": "MBT", "exchange": "CME", "currency": "USD"},   # Micro Bitcoin
    "ZT":  {"symbol": "ZT",  "exchange": "CBOT", "currency": "USD"},
    "ZN":  {"symbol": "ZN",  "exchange": "CBOT", "currency": "USD"},
    "SR3": {"symbol": "SR3", "exchange": "CME", "currency": "USD"},   # 3M SOFR
}


@dataclass
class ResolvedContract:
    symbol: str
    sec_type: str
    con_id: int
    exchange: str
    currency: str
    local_symbol: str = ""
    last_trade_date: str = ""        # YYYYMMDD（期货到期）
    multiplier: str = ""
    resolved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw: Optional[object] = None     # 原始 ib_insync Contract/ContractDetails

    @property
    def is_locked(self) -> bool:
        return self.con_id > 0


class ContractResolutionError(RuntimeError):
    pass


class IBKRContractResolver:
    """
    用法（ib_insync）：
        from ib_insync import IB
        ib = IB(); ib.connect("127.0.0.1", 7497, clientId=11)   # 7497 = 模拟盘
        resolver = IBKRContractResolver(ib)
        rc = resolver.resolve("MNQ")        # 自动选近月并锁 conId
        # 之后用 rc.raw（已带 conId 的 Contract）下单
    """

    def __init__(self, ib=None):
        self.ib = ib
        self._cache: Dict[str, ResolvedContract] = {}

    # ── 公共入口 ──────────────────────────────────────────────────────────
    def resolve(self, symbol: str, prefer_front_month: bool = True,
                refresh: bool = False) -> ResolvedContract:
        if not refresh and symbol in self._cache:
            return self._cache[symbol]

        if symbol in FX_SPECS:
            rc = self._resolve_fx(symbol)
        elif symbol in CRYPTO_SPECS:
            rc = self._resolve_crypto(symbol)
        elif symbol in FUT_SPECS:
            rc = self._resolve_future(symbol, prefer_front_month)
        else:
            raise ContractResolutionError(f"未知品种: {symbol}")

        if not rc.is_locked:
            raise ContractResolutionError(
                f"{symbol} 未能锁定 conId，禁止下单（避免 CONTFUT/ambiguity 风险）")
        self._cache[symbol] = rc
        return rc

    def get_cached(self, symbol: str) -> Optional[ResolvedContract]:
        return self._cache.get(symbol)

    # ── FX ────────────────────────────────────────────────────────────────
    def _resolve_fx(self, symbol: str) -> ResolvedContract:
        spec = FX_SPECS[symbol]
        if self.ib is None:
            raise ContractResolutionError("未连接 IB，无法解析（拒绝在未解析状态下下单）")
        from ib_insync import Forex
        c = Forex(spec["symbol"] + spec["currency"])
        details = self.ib.reqContractDetails(c)
        if not details:
            raise ContractResolutionError(f"FX 合约无返回: {symbol}")
        cd = details[0]
        con = cd.contract
        return ResolvedContract(
            symbol=symbol, sec_type="CASH", con_id=con.conId,
            exchange=con.exchange or spec["exchange"], currency=con.currency,
            local_symbol=con.localSymbol, raw=con)

    # ── 期货：展开到期月，选近月/主力 ─────────────────────────────────────
    def _resolve_crypto(self, symbol: str) -> ResolvedContract:
        spec = CRYPTO_SPECS[symbol]
        if self.ib is None:
            raise ContractResolutionError("未连接 IB，无法解析（拒绝在未解析状态下下单）")
        from ib_insync import Crypto
        c = Crypto(spec["symbol"], spec["exchange"], spec["currency"])
        details = self.ib.reqContractDetails(c)
        if not details:
            raise ContractResolutionError(f"现货加密合约无返回: {symbol}")
        con = details[0].contract
        return ResolvedContract(
            symbol=symbol, sec_type="CRYPTO", con_id=con.conId,
            exchange=con.exchange or spec["exchange"], currency=con.currency,
            local_symbol=con.localSymbol, raw=con)

    def _resolve_future(self, symbol: str, prefer_front_month: bool) -> ResolvedContract:
        spec = FUT_SPECS[symbol]
        if self.ib is None:
            raise ContractResolutionError("未连接 IB，无法解析（拒绝在未解析状态下下单）")
        from ib_insync import Future
        # 模糊模板：不指定到期月，让 IBKR 返回所有可交易月份
        template = Future(symbol=spec["symbol"], exchange=spec["exchange"],
                          currency=spec["currency"])
        details = self.ib.reqContractDetails(template)
        if not details:
            raise ContractResolutionError(f"期货合约无返回: {symbol}")

        # 收集所有 (到期日, ContractDetails)，按到期升序
        dated: List = []
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        for cd in details:
            ltd = cd.contract.lastTradeDateOrContractMonth or ""
            ltd8 = (ltd + "01")[:8] if len(ltd) == 6 else ltd[:8]
            if ltd8 and ltd8 >= today:        # 只取未到期
                dated.append((ltd8, cd))
        if not dated:
            raise ContractResolutionError(f"{symbol} 无未到期合约")
        dated.sort(key=lambda x: x[0])

        # 主力选择：默认近月；可扩展为按 OI/成交量选主力（需额外行情请求）
        chosen = dated[0][1] if prefer_front_month else dated[min(1, len(dated) - 1)][1]
        con = chosen.contract
        return ResolvedContract(
            symbol=symbol, sec_type="FUT", con_id=con.conId,
            exchange=con.exchange or spec["exchange"], currency=con.currency,
            local_symbol=con.localSymbol,
            last_trade_date=con.lastTradeDateOrContractMonth,
            multiplier=str(con.multiplier), raw=con)


# ── 离线模板（无 IB 连接时，仅用于结构展示，永远不会被允许下单）──────────────
def offline_template(symbol: str) -> Dict[str, str]:
    """返回模糊模板字典；is_locked 永远为 False，提醒必须先解析。"""
    if symbol in FX_SPECS:
        return {**FX_SPECS[symbol], "secType": "CASH", "conId": "0",
                "note": "未解析，禁止下单"}
    if symbol in FUT_SPECS:
        return {**FUT_SPECS[symbol], "secType": "FUT", "conId": "0",
                "note": "未解析，必须先 reqContractDetails 选月份"}
    raise ContractResolutionError(f"未知品种: {symbol}")
