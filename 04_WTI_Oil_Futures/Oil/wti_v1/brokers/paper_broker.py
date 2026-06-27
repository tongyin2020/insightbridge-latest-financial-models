"""
WTI v1 — Paper Broker（模拟经纪商）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
完全模拟真实平台行为：
- 模拟滑点（可配置）
- 模拟成交延迟
- 模拟点差影响
- 真实记录所有订单和持仓

切换到真实平台时，只需替换这个模块，
上层的信号/风控/复盘逻辑不变。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
import random
from datetime import datetime
from typing import Optional, Dict, List
import asyncio

from models.core import (
    Order, Position, Tick, Direction,
    OrderStatus, ExitReason, TradeRecord
)

logger = logging.getLogger(__name__)


class PaperBroker:
    """
    模拟经纪商。
    用于历史验证和模拟盘阶段。
    接口设计与真实broker接口保持一致，确保日后无缝切换。
    """

    def __init__(
        self,
        initial_equity: float = 50000.0,
        simulated_slippage_ticks: float = 1.0,   # 模拟滑点（tick）
        simulated_fill_delay_ms: int = 150,        # 模拟成交延迟（毫秒）
        commission_per_rt: float = 4.0,            # 每手往返手续费
    ):
        self.equity = initial_equity
        self.initial_equity = initial_equity
        self.slippage_ticks = simulated_slippage_ticks
        self.fill_delay_ms = simulated_fill_delay_ms
        self.commission_per_rt = commission_per_rt

        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._trade_records: List[TradeRecord] = []
        self._current_tick: Optional[Tick] = None

        logger.info(
            f"[PaperBroker] 初始化 | 账户={initial_equity:,.0f} | "
            f"滑点={simulated_slippage_ticks}t | 手续费={commission_per_rt}/RT"
        )

    # ─────────────────────────────────────────
    # 行情更新
    # ─────────────────────────────────────────

    def update_tick(self, tick: Tick):
        """接收最新报价，检查止损"""
        self._current_tick = tick
        self._check_stop_losses(tick)

    # ─────────────────────────────────────────
    # 下单
    # ─────────────────────────────────────────

    async def submit_order(self, order: Order) -> Order:
        """提交订单（模拟成交延迟）"""
        self._orders[order.id] = order
        logger.info(
            f"[PaperBroker] 订单提交 | {order.direction.value} {order.quantity}手 | "
            f"类型={order.order_type}"
        )

        # 模拟延迟
        await asyncio.sleep(self.fill_delay_ms / 1000)

        # 模拟成交
        fill_price = self._simulate_fill_price(order)
        order.filled_price = fill_price
        order.filled_at = datetime.utcnow()
        order.status = OrderStatus.FILLED

        logger.info(f"[PaperBroker] 订单成交 | 价格={fill_price:.2f} | 订单ID={order.id}")
        return order

    def open_position(self, order: Order, stop_loss: float) -> Position:
        """根据成交订单开仓"""
        pos = Position(
            symbol=order.symbol,
            direction=order.direction,
            quantity=order.quantity,
            entry_price=order.filled_price,
            stop_loss_price=stop_loss,
            signal_id=order.signal_id,
        )
        self._positions[pos.id] = pos
        logger.info(
            f"[PaperBroker] 开仓 | {pos.direction.value} {pos.quantity}手 @ {pos.entry_price:.2f} | "
            f"止损={stop_loss:.2f}"
        )
        return pos

    async def close_position(self, position_id: str, reason: ExitReason) -> Optional[TradeRecord]:
        """平仓"""
        pos = self._positions.get(position_id)
        if not pos or not pos.is_open:
            logger.warning(f"[PaperBroker] 平仓失败，持仓不存在或已关闭: {position_id}")
            return None

        if self._current_tick is None:
            logger.error("[PaperBroker] 无当前报价，无法平仓")
            return None

        # 模拟延迟
        await asyncio.sleep(self.fill_delay_ms / 1000)

        # 平仓价格（含滑点）
        if pos.direction == Direction.LONG:
            exit_price = self._current_tick.bid - (self.slippage_ticks * 0.01)
        else:
            exit_price = self._current_tick.ask + (self.slippage_ticks * 0.01)

        pos.exit_price = round(exit_price, 2)
        pos.exit_reason = reason
        pos.closed_at = datetime.utcnow()
        pos.is_open = False

        # 计算PnL
        if pos.direction == Direction.LONG:
            raw_pnl = (pos.exit_price - pos.entry_price) * pos.quantity * 1000
        else:
            raw_pnl = (pos.entry_price - pos.exit_price) * pos.quantity * 1000

        commission = self.commission_per_rt * pos.quantity
        net_pnl = raw_pnl - commission
        self.equity += net_pnl

        # 生成交易记录
        record = TradeRecord(
            date=pos.opened_at.strftime("%Y-%m-%d"),
            symbol=pos.symbol,
            direction=pos.direction.value,
            entry_price=pos.entry_price,
            exit_price=pos.exit_price,
            quantity=pos.quantity,
            pnl_usd=round(net_pnl, 2),
            hold_minutes=pos.hold_minutes,
            exit_reason=reason.value,
        )
        self._trade_records.append(record)

        logger.info(
            f"[PaperBroker] 平仓 | {pos.direction.value} @ {pos.exit_price:.2f} | "
            f"PnL={net_pnl:+.2f} | 原因={reason.value} | "
            f"账户净值={self.equity:,.2f}"
        )

        return record

    # ─────────────────────────────────────────
    # 账户查询
    # ─────────────────────────────────────────

    @property
    def open_positions(self) -> List[Position]:
        return [p for p in self._positions.values() if p.is_open]

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.open_positions)

    @property
    def net_liquidation_value(self) -> float:
        return self.equity + self.total_unrealized_pnl

    def get_trade_summary(self) -> dict:
        """生成交易统计摘要（复盘用）"""
        records = self._trade_records
        if not records:
            return {"message": "暂无交易记录"}

        wins = [r for r in records if r.pnl_usd > 0]
        losses = [r for r in records if r.pnl_usd <= 0]
        total_pnl = sum(r.pnl_usd for r in records)

        return {
            "总交易笔数": len(records),
            "盈利笔数": len(wins),
            "亏损笔数": len(losses),
            "胜率": f"{len(wins)/len(records):.1%}" if records else "0%",
            "总PnL": f"${total_pnl:+,.2f}",
            "平均盈利": f"${sum(r.pnl_usd for r in wins)/len(wins):+.2f}" if wins else "$0",
            "平均亏损": f"${sum(r.pnl_usd for r in losses)/len(losses):+.2f}" if losses else "$0",
            "盈亏比": f"{abs(sum(r.pnl_usd for r in wins)/sum(r.pnl_usd for r in losses)):.2f}" if losses and wins else "N/A",
            "平均持仓时间": f"{sum(r.hold_minutes for r in records)/len(records):.1f}分钟",
            "当前净值": f"${self.equity:,.2f}",
            "收益率": f"{(self.equity - self.initial_equity)/self.initial_equity:.1%}",
        }

    # ─────────────────────────────────────────
    # 内部方法
    # ─────────────────────────────────────────

    def _simulate_fill_price(self, order: Order) -> float:
        """模拟成交价格（含滑点）"""
        if self._current_tick is None:
            return 0.0

        slippage = self.slippage_ticks * 0.01
        # 随机化一半滑点，模拟真实情况
        actual_slippage = slippage * random.uniform(0.5, 1.5)

        if order.direction == Direction.LONG:
            return round(self._current_tick.ask + actual_slippage, 2)
        else:
            return round(self._current_tick.bid - actual_slippage, 2)

    def _check_stop_losses(self, tick: Tick):
        """检查所有持仓的止损（同步调用，实盘中需改为async）"""
        for pos in self.open_positions:
            pos.current_price = tick.mid
            hit = False

            if pos.direction == Direction.LONG and tick.bid <= pos.stop_loss_price:
                hit = True
            elif pos.direction == Direction.SHORT and tick.ask >= pos.stop_loss_price:
                hit = True

            if hit:
                logger.warning(
                    f"[PaperBroker] 止损触发 | {pos.direction.value} "
                    f"止损价={pos.stop_loss_price:.2f} 当前={tick.mid:.2f}"
                )
                # 注意：这里使用asyncio.ensure_future是因为check是同步的
                asyncio.ensure_future(
                    self.close_position(pos.id, ExitReason.STOP_LOSS)
                )
