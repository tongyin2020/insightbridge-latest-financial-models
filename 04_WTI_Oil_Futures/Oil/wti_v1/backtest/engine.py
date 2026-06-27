"""
WTI v1 — 回测引擎
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bar-by-bar 回测：逐根K线模拟，支持事件回放。
原则：回测必须尽可能模拟真实执行条件
- 模拟滑点
- 只用已知数据（无未来数据泄露）
- 记录每个决策的原因
- 按样本内 / 样本外分期验证
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field
import json

from models.core import (
    Bar, Tick, Indicators, MarketEvent, EventPriority,
    Regime, Direction, Signal, SignalStatus, TradeRecord
)
from services.regime_service import RegimeService
from services.signal_service import SignalService
from services.risk_service import RiskService
from brokers.paper_broker import PaperBroker
from config.settings import RISK, CONFIRM, REGIME, HOLDING, EVENT_CONFIRM_WINDOW

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    start_date: str                         # "2023-01-01"
    end_date: str                           # "2024-06-30"
    in_sample_end: Optional[str] = None     # 样本内结束（为空则全程）
    initial_equity: float = 50000.0
    slippage_ticks: float = 1.5            # 回测中稍微保守一点
    commission_per_rt: float = 4.0


@dataclass
class BacktestResult:
    config: BacktestConfig
    trade_records: List[TradeRecord] = field(default_factory=list)
    regime_history: List[dict] = field(default_factory=list)
    signal_history: List[dict] = field(default_factory=list)
    equity_curve: List[Tuple[str, float]] = field(default_factory=list)
    final_equity: float = 0.0

    def summary(self) -> dict:
        records = self.trade_records
        if not records:
            return {"message": "无交易记录"}

        wins = [r for r in records if r.pnl_usd > 0]
        losses = [r for r in records if r.pnl_usd <= 0]
        total_pnl = sum(r.pnl_usd for r in records)
        max_dd = self._calc_max_drawdown()

        return {
            "回测区间": f"{self.config.start_date} ~ {self.config.end_date}",
            "初始净值": f"${self.config.initial_equity:,.0f}",
            "最终净值": f"${self.final_equity:,.2f}",
            "总收益率": f"{(self.final_equity - self.config.initial_equity)/self.config.initial_equity:.1%}",
            "总交易": len(records),
            "胜率": f"{len(wins)/len(records):.1%}" if records else "0%",
            "盈利笔": len(wins),
            "亏损笔": len(losses),
            "平均盈利": f"${sum(r.pnl_usd for r in wins)/len(wins):.2f}" if wins else "$0",
            "平均亏损": f"${sum(r.pnl_usd for r in losses)/len(losses):.2f}" if losses else "$0",
            "盈亏比": f"{abs(sum(r.pnl_usd for r in wins))/abs(sum(r.pnl_usd for r in losses)):.2f}" if losses and wins else "N/A",
            "最大回撤": f"${max_dd:.2f}",
            "平均持仓": f"{sum(r.hold_minutes for r in records)/len(records):.1f}分钟",
        }

    def _calc_max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0][1]
        max_dd = 0.0
        for _, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        return max_dd

    def worst_periods(self) -> List[dict]:
        """找出最差时段（用于改进模型）"""
        if not self.trade_records:
            return []
        by_hour: Dict[int, List[float]] = {}
        for r in self.trade_records:
            # 简化：按小时统计
            h = 0  # 实际使用时从timestamp提取
            by_hour.setdefault(h, []).append(r.pnl_usd)
        return []

    def export_json(self, path: str):
        data = {
            "summary": self.summary(),
            "trade_count": len(self.trade_records),
            "equity_curve_points": len(self.equity_curve),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[Backtest] 结果已导出: {path}")


class BacktestEngine:
    """
    回测引擎。
    输入：历史K线数组 + 历史事件数组
    输出：BacktestResult

    使用方式：
        bars = load_wti_bars("2023-01-01", "2024-06-30")
        events = load_historical_events("2023-01-01", "2024-06-30")
        config = BacktestConfig(start_date="2023-01-01", end_date="2024-06-30")
        engine = BacktestEngine(config)
        result = await engine.run(bars, events)
        print(result.summary())
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.regime_svc = RegimeService(REGIME)
        self.signal_svc = SignalService(CONFIRM)
        self.risk_svc = RiskService(RISK)
        self.broker = PaperBroker(
            initial_equity=config.initial_equity,
            simulated_slippage_ticks=config.slippage_ticks,
            commission_per_rt=config.commission_per_rt,
        )
        self.result = BacktestResult(config=config)

    async def run(
        self,
        bars: List[Bar],
        events: List[MarketEvent],
        indicators_list: List[Indicators],
    ) -> BacktestResult:
        """
        执行回测主循环。
        bars, events, indicators_list 必须按时间戳排序。
        """
        logger.info(
            f"[Backtest] 开始 | {self.config.start_date} ~ {self.config.end_date} | "
            f"{len(bars)}根K线 | {len(events)}个事件"
        )

        event_idx = 0
        equity = self.config.initial_equity

        for i, (bar, ind) in enumerate(zip(bars, indicators_list)):
            # ① 检查当前K线之前有无事件（按时间戳对齐）
            while event_idx < len(events) and events[event_idx].timestamp <= bar.timestamp:
                evt = events[event_idx]
                priority = evt.priority.value
                window = EVENT_CONFIRM_WINDOW.get(priority, (0, 0))
                if window[1] > 0:
                    self.regime_svc.on_market_event(evt, window[1])
                    # 构造当时的tick（用bar的close近似）
                    fake_tick = Tick(
                        timestamp=bar.timestamp,
                        bid=bar.close - 0.02,
                        ask=bar.close + 0.02,
                        last=bar.close,
                        volume=bar.volume,
                    )
                    self.signal_svc.on_event(evt, fake_tick)
                event_idx += 1

            # ② 更新环境
            self.regime_svc.update(ind)
            self.regime_svc.check_event_window_expiry()
            current_regime = self.regime_svc.current

            # ③ 构造当前bar的tick（用close近似）
            tick = Tick(
                timestamp=bar.timestamp,
                bid=bar.close - 0.02,
                ask=bar.close + 0.02,
                last=bar.close,
                volume=bar.volume,
            )
            self.broker.update_tick(tick)

            # ④ 检查持仓时间
            for pos in self.broker.open_positions:
                if pos.hold_minutes > HOLDING.max_hold_min:
                    record = await self.broker.close_position(pos.id, __import__('models.core', fromlist=['ExitReason']).ExitReason.TIME_EXIT)
                    if record:
                        self.result.trade_records.append(record)
                        self.risk_svc.register_trade_result(record.pnl_usd, self.broker.equity)

            # ⑤ 信号确认尝试
            sig = self.signal_svc.on_tick(tick, ind, current_regime)
            if sig and sig.status == SignalStatus.ACCEPTED:
                # 记录信号
                self.result.signal_history.append({
                    "ts": bar.timestamp.isoformat(),
                    "direction": sig.direction.value if sig.direction else None,
                    "regime": current_regime.value,
                })

                # 风控检查
                check = self.risk_svc.check_signal(sig, tick, self.broker.equity)
                if check.allowed:
                    from models.core import Order
                    order = Order(
                        symbol="CL",
                        direction=sig.direction,
                        quantity=check.position_size,
                        signal_id=sig.id,
                    )
                    filled = await self.broker.submit_order(order)
                    self.broker.open_position(filled, sig.stop_loss_price)

            # ⑥ 记录净值曲线
            if i % 20 == 0:  # 每20根K线记录一次
                self.result.equity_curve.append(
                    (bar.timestamp.strftime("%Y-%m-%d %H:%M"), self.broker.equity)
                )

        # 最终平仓所有持仓
        for pos in self.broker.open_positions:
            record = await self.broker.close_position(pos.id, __import__('models.core', fromlist=['ExitReason']).ExitReason.TIME_EXIT)
            if record:
                self.result.trade_records.append(record)

        self.result.final_equity = self.broker.equity
        self.result.trade_records.extend(self.broker._trade_records)

        summary = self.result.summary()
        logger.info("[Backtest] 完成")
        for k, v in summary.items():
            logger.info(f"  {k}: {v}")

        return self.result
