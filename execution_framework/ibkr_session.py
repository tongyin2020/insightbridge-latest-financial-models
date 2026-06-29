"""
ibkr_session.py
═══════════════════════════════════════════════════════════════════════════════
TWS / IB Gateway 会话层（第三优先实现）：真实连接 IBKR 模拟盘所需的稳健性组件
  1. 连接管理：7497（TWS 模拟盘）/ 4002（IB Gateway 模拟盘）/
     7496（TWS 实盘）/ 4001（IB Gateway 实盘），clientId、超时、握手等待。
  2. IBKR 错误码处理：分类为 INFO / WARN / RETRY / FATAL，并暴露回调。
  3. 断线重连：connectedEvent / disconnectedEvent 监听 + 指数退避重连。
  4. 对账：reqOpenOrders + reqExecutions + positions，对比本地账本，输出差异。
  5. 按 OI/成交量选主力合约（取代"默认近月"）。

依赖 ib_insync。本模块只做"连接 + 稳健性 + 对账"，不直接产生交易决策。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("ibkr_session")


# ── IBKR 错误码分类 ──────────────────────────────────────────────────────────
# 参考 IBKR API message codes。分类用于决定"忽略 / 告警 / 重试 / 致命停机"。
ERROR_CLASS: Dict[int, str] = {
    # INFO / 行情农场连接状态（非错误）
    2104: "INFO", 2106: "INFO", 2158: "INFO", 2107: "INFO", 2119: "INFO",
    # WARN —— 数据相关，可继续但需记录
    2100: "WARN", 2103: "WARN", 2105: "WARN", 2108: "WARN", 2150: "WARN",
    354:  "WARN",   # 未订阅行情
    10167: "WARN",  # 请求的市场数据不可用
    # RETRY —— 连接/限流类，应退避重试
    1100: "RETRY",  # 与 TWS 的连接已断开
    1101: "RETRY",  # 连接已恢复但数据丢失（需重订阅）
    1102: "RETRY",  # 连接已恢复且数据维持
    100:  "RETRY",  # 超出消息速率
    # FATAL —— 下单/合约/权限类，需人工或硬停
    200:  "FATAL",  # 合约不明（ambiguous / 未解析）
    201:  "FATAL",  # 订单被拒（常见：保证金不足）
    203:  "FATAL",  # 该账户不允许此证券/操作
    321:  "FATAL",  # 服务器错误：订单校验失败
    10147: "WARN",  # 要取消的订单不存在
    10148: "WARN",  # 要取消的订单无法取消
}


def classify_error(code: int) -> str:
    return ERROR_CLASS.get(code, "WARN")


@dataclass
class ReconResult:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    broker_positions: Dict[str, float] = field(default_factory=dict)
    local_positions: Dict[str, float] = field(default_factory=dict)
    position_mismatches: Dict[str, Dict[str, float]] = field(default_factory=dict)
    open_orders: List[Dict[str, Any]] = field(default_factory=list)
    recent_executions: List[Dict[str, Any]] = field(default_factory=list)
    in_sync: bool = True


class IBKRSession:
    """
    用法（模拟盘）：
        sess = IBKRSession(host="127.0.0.1", port=4002, client_id=21)
        sess.connect()
        sess.on_fatal = lambda code, msg: pipeline.halt(f"IBKR {code}: {msg}")
        ...
        recon = sess.reconcile(local_positions={"MNQ": 1})
        if not recon.in_sync: pipeline.halt("position desync")
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4002,
                 client_id: int = 21, connect_timeout: float = 8.0,
                 max_reconnect_attempts: int = 6):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.connect_timeout = connect_timeout
        self.max_reconnect_attempts = max_reconnect_attempts

        self.ib = None
        self._ib_insync_ok = True
        try:
            from ib_insync import IB  # noqa: F401
        except Exception:             # noqa: BLE001
            self._ib_insync_ok = False

        self._reconnecting = threading.Lock()
        # 外部可挂的回调
        self.on_fatal: Optional[Callable[[int, str], None]] = None
        self.on_retry: Optional[Callable[[int, str], None]] = None
        self.on_reconnect: Optional[Callable[[], None]] = None

    # ── 连接 ──────────────────────────────────────────────────────────────
    @property
    def is_paper(self) -> bool:
        return self.port in (7497, 4002)

    def connect(self) -> bool:
        if not self._ib_insync_ok:
            raise RuntimeError("未安装 ib_insync，无法连接 TWS")
        from ib_insync import IB
        if self.ib is None:
            self.ib = IB()
            self.ib.errorEvent += self._on_error
            self.ib.disconnectedEvent += self._on_disconnected
        if self.ib.isConnected():
            return True
        self.ib.connect(self.host, self.port, clientId=self.client_id,
                        timeout=self.connect_timeout)
        ok = self.ib.isConnected()
        if ok:
            logger.info("Connected to TWS %s:%s (paper=%s, clientId=%s)",
                        self.host, self.port, self.is_paper, self.client_id)
        return ok

    def disconnect(self) -> None:
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()

    # ── 错误处理 ──────────────────────────────────────────────────────────
    def _on_error(self, reqId, errorCode, errorString, contract=None):
        cls = classify_error(errorCode)
        msg = f"[{cls}] IBKR {errorCode}: {errorString} (reqId={reqId})"
        if cls == "INFO":
            logger.debug(msg)
        elif cls == "WARN":
            logger.warning(msg)
        elif cls == "RETRY":
            logger.warning(msg)
            if errorCode in (1100, 1101):
                self._schedule_reconnect()
            if self.on_retry:
                self.on_retry(errorCode, errorString)
        elif cls == "FATAL":
            logger.error(msg)
            if self.on_fatal:
                self.on_fatal(errorCode, errorString)

    def _on_disconnected(self):
        logger.warning("TWS disconnected event received")
        self._schedule_reconnect()

    # ── 断线重连（指数退避）────────────────────────────────────────────────
    def _schedule_reconnect(self) -> None:
        if not self._reconnecting.acquire(blocking=False):
            return  # 已有重连在进行
        try:
            backoff = 1.0
            for attempt in range(1, self.max_reconnect_attempts + 1):
                if self.ib and self.ib.isConnected():
                    return
                logger.warning("Reconnect attempt %s/%s in %.1fs ...",
                               attempt, self.max_reconnect_attempts, backoff)
                time.sleep(backoff)
                try:
                    self.ib.connect(self.host, self.port,
                                    clientId=self.client_id,
                                    timeout=self.connect_timeout)
                except Exception as exc:   # noqa: BLE001
                    logger.warning("Reconnect failed: %s", exc)
                if self.ib and self.ib.isConnected():
                    logger.info("Reconnected to TWS")
                    # 连接恢复后重新拉取未结订单与持仓（1101 会丢数据）
                    try:
                        self.ib.reqOpenOrders()
                        self.ib.reqPositions()
                    except Exception:      # noqa: BLE001
                        pass
                    if self.on_reconnect:
                        self.on_reconnect()
                    return
                backoff = min(backoff * 2, 30.0)
            logger.error("Reconnect exhausted after %s attempts",
                         self.max_reconnect_attempts)
            if self.on_fatal:
                self.on_fatal(1100, "reconnect_exhausted")
        finally:
            self._reconnecting.release()

    # ── 按 OI/成交量选主力 ────────────────────────────────────────────────
    def resolve_front_liquid_future(self, symbol: str, exchange: str,
                                    currency: str = "USD",
                                    top_n: int = 3) -> Optional[object]:
        """返回 OI/成交量最高的近月合约（已带 conId）。
        策略：reqContractDetails 取最近 top_n 个未到期月 -> 各请求快照行情
        -> 选 (openInterest 优先，其次 volume) 最大者。"""
        if not (self.ib and self.ib.isConnected()):
            return None
        from ib_insync import Future
        template = Future(symbol=symbol, exchange=exchange, currency=currency)
        details = self.ib.reqContractDetails(template)
        if not details:
            return None
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        dated = []
        for cd in details:
            ltd = (cd.contract.lastTradeDateOrContractMonth or "")
            ltd8 = (ltd + "01")[:8] if len(ltd) == 6 else ltd[:8]
            if ltd8 and ltd8 >= today:
                dated.append((ltd8, cd.contract))
        if not dated:
            return None
        dated.sort(key=lambda x: x[0])
        candidates = [c for _, c in dated[:top_n]]

        best, best_key = None, -1.0
        for con in candidates:
            try:
                tkr = self.ib.reqMktData(con, genericTickList="", snapshot=True)
                self.ib.sleep(1.5)
                oi = _safe_num(getattr(tkr, "futuresOpenInterest", None))
                vol = _safe_num(getattr(tkr, "volume", None))
                key = oi if oi > 0 else vol     # OI 优先，缺失则用成交量
                if key > best_key:
                    best, best_key = con, key
            except Exception as exc:            # noqa: BLE001
                logger.warning("OI snapshot failed for %s: %s", con.localSymbol, exc)
        # 全部拿不到行情时回退近月
        return best or candidates[0]

    # ── 对账 ──────────────────────────────────────────────────────────────
    def reconcile(self, local_positions: Optional[Dict[str, float]] = None,
                  exec_lookback: int = 50) -> ReconResult:
        """对比券商持仓/未结订单/成交 与 本地账本。"""
        res = ReconResult()
        if not (self.ib and self.ib.isConnected()):
            res.in_sync = False
            return res

        # 券商持仓
        for p in self.ib.positions():
            sym = p.contract.localSymbol or p.contract.symbol
            res.broker_positions[sym] = res.broker_positions.get(sym, 0.0) + float(p.position)

        # 未结订单
        for tr in self.ib.openTrades():
            res.open_orders.append({
                "ref": tr.order.orderRef, "action": tr.order.action,
                "qty": tr.order.totalQuantity, "type": tr.order.orderType,
                "status": tr.orderStatus.status,
                "symbol": tr.contract.localSymbol or tr.contract.symbol})

        # 近期成交
        try:
            fills = self.ib.fills()[-exec_lookback:]
            for f in fills:
                res.recent_executions.append({
                    "ref": f.execution.orderRef, "side": f.execution.side,
                    "shares": f.execution.shares, "price": f.execution.price,
                    "symbol": f.contract.localSymbol or f.contract.symbol,
                    "time": str(f.execution.time)})
        except Exception:                       # noqa: BLE001
            pass

        # 与本地账本比对
        local = local_positions or {}
        res.local_positions = dict(local)
        all_syms = set(res.broker_positions) | set(local)
        for s in all_syms:
            b = res.broker_positions.get(s, 0.0)
            l = local.get(s, 0.0)
            if abs(b - l) > 1e-9:
                res.position_mismatches[s] = {"broker": b, "local": l}
        res.in_sync = len(res.position_mismatches) == 0
        if not res.in_sync:
            logger.error("Position desync: %s", res.position_mismatches)
        return res


def _safe_num(x) -> float:
    try:
        v = float(x)
        return v if v == v else 0.0   # 过滤 NaN
    except (TypeError, ValueError):
        return 0.0
