"""
WTI v1 — 系统主入口
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
系统启动顺序：
1. 初始化配置和日志
2. 初始化事件总线
3. 初始化各服务模块
4. 注册事件订阅
5. 启动数据接入
6. 进入主事件循环

停止方式：
- 键盘 Ctrl+C → 优雅停止
- Kill switch → 立即停止所有执行（持仓需手动处理）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

# 系统配置
from config.settings import RISK, HOLDING, CONFIRM, REGIME, BROKER

# 事件总线
from app.event_bus import (
    get_bus,
    NewBarEvent, NewTickEvent, MarketEventReceived,
    SignalGeneratedEvent, RiskHaltEvent, KillSwitchEvent,
    SystemStartEvent, SystemStopEvent, PositionClosedEvent,
)

# 服务
from services.risk_service import RiskService
from services.regime_service import RegimeService
from services.signal_service import SignalService

# Broker
from brokers.paper_broker import PaperBroker

# 模型
from models.core import Regime, ExitReason

# ─────────────────────────────────────────────
# 日志配置
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/wti_v1_{datetime.utcnow().strftime('%Y%m%d')}.log"),
    ]
)
logger = logging.getLogger("WTI_v1")


# ─────────────────────────────────────────────
# 系统主类
# ─────────────────────────────────────────────

class WTISystem:
    """
    WTI v1 系统协调器。
    负责：模块装配、事件路由、生命周期管理。
    """

    def __init__(self):
        self.bus = get_bus()
        self.risk = RiskService(RISK)
        self.regime = RegimeService(REGIME)
        self.signal = SignalService(CONFIRM)
        self.broker = PaperBroker(
            initial_equity=RISK.account_equity,
            simulated_slippage_ticks=1.0,
        )
        self._running = False
        logger.info("[System] 所有模块初始化完成")

    def setup(self):
        """注册所有事件订阅"""
        bus = self.bus

        # 新K线 → 更新指标 → 更新环境 → 检查信号
        bus.subscribe(NewBarEvent, self._on_new_bar)

        # 新报价 → 止损检查 → 持仓监控
        bus.subscribe(NewTickEvent, self._on_new_tick)

        # 市场事件 → 环境切换 → 启动确认
        bus.subscribe(MarketEventReceived, self._on_market_event)

        # 信号生成 → 风控检查 → 执行
        bus.subscribe(SignalGeneratedEvent, self._on_signal)

        # Kill switch
        bus.subscribe(KillSwitchEvent, self._on_kill_switch)

        # 持仓关闭 → 更新风控状态
        bus.subscribe(PositionClosedEvent, self._on_position_closed)

        logger.info("[System] 事件订阅注册完成")

    async def start(self):
        """启动系统"""
        self._running = True
        logger.info("=" * 60)
        logger.info("  WTI v1 系统启动")
        logger.info(f"  模式: {BROKER.mode.upper()}")
        logger.info(f"  品种: {__import__('config.settings', fromlist=['SYMBOL']).SYMBOL}")
        logger.info(f"  账户: ${RISK.account_equity:,.0f}")
        logger.info("=" * 60)

        await self.bus.publish(SystemStartEvent())

        # 注册系统信号（Ctrl+C 优雅停止）
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.stop("系统信号")))

        # 启动事件总线（主循环）
        await self.bus.run()

    async def stop(self, reason: str = "normal"):
        """优雅停止"""
        logger.info(f"[System] 正在停止: {reason}")
        self._running = False

        # 打印最终统计
        summary = self.broker.get_trade_summary()
        logger.info("=" * 60)
        logger.info("  最终交易统计")
        for k, v in summary.items():
            logger.info(f"  {k}: {v}")
        logger.info(f"  风控状态: {self.risk.summary}")
        logger.info("=" * 60)

        await self.bus.publish(SystemStopEvent(reason=reason))
        await self.bus.stop()

    # ─────────────────────────────────────────
    # 事件处理器
    # ─────────────────────────────────────────

    async def _on_new_bar(self, event: NewBarEvent):
        """新K线：更新环境状态"""
        # 注：实际使用中，indicators由指标服务计算后附带
        # v1 简化：直接在此处触发环境检查
        self.regime.check_event_window_expiry()

    async def _on_new_tick(self, event: NewTickEvent):
        """新报价：更新broker止损"""
        self.broker.update_tick(event.tick)

        # 持仓时间管理
        for pos in self.broker.open_positions:
            if pos.hold_minutes > HOLDING.max_hold_min:
                logger.info(f"[System] 持仓超时，执行时间退出 | 持续={pos.hold_minutes:.1f}分钟")
                await self.broker.close_position(pos.id, ExitReason.TIME_EXIT)
            elif pos.hold_minutes > HOLDING.early_exit_no_momentum_min:
                # TODO: 检查动量是否已衰减（v1.1实现）
                pass

    async def _on_market_event(self, event: MarketEventReceived):
        """市场事件：切换环境，启动确认窗口"""
        mkt_event = event.event
        logger.info(f"[System] 市场事件: [{mkt_event.priority}] {mkt_event.headline[:60]}")

        from config.settings import EVENT_CONFIRM_WINDOW
        priority = mkt_event.priority.value
        window_range = EVENT_CONFIRM_WINDOW.get(priority, (0, 0))
        confirm_window_sec = window_range[1]  # 用最大窗口

        self.regime.on_market_event(mkt_event, confirm_window_sec)

        if self.broker._current_tick:
            self.signal.on_event(mkt_event, self.broker._current_tick)

    async def _on_signal(self, event: SignalGeneratedEvent):
        """信号：风控检查 → 执行"""
        sig = event.signal
        tick = self.broker._current_tick

        if tick is None:
            logger.warning("[System] 信号到达但无当前报价，跳过")
            return

        # 风控检查（绝对不可绕过）
        check = self.risk.check_signal(sig, tick, self.broker.equity)
        if not check.allowed:
            logger.warning(f"[System] 信号被风控拒绝: {check.reason}")
            return

        # 执行（paper broker）
        from models.core import Order
        order = Order(
            symbol=sig.symbol,
            direction=sig.direction,
            quantity=check.position_size,
            order_type="market",
            signal_id=sig.id,
        )
        filled_order = await self.broker.submit_order(order)
        position = self.broker.open_position(filled_order, sig.stop_loss_price)

        logger.info(
            f"[System] 🟢 开仓成功 | {sig.direction.value} {check.position_size}手 @ "
            f"{filled_order.filled_price:.2f} | 止损={sig.stop_loss_price:.2f}"
        )

    async def _on_kill_switch(self, event: KillSwitchEvent):
        """Kill switch：立即停止所有执行"""
        self.risk.activate_kill_switch(event.triggered_by)
        logger.critical("[System] ⚠️  KILL SWITCH 激活，停止所有自动执行")
        # 注意：持仓不自动平仓（需人工确认），只停止新交易

    async def _on_position_closed(self, event: PositionClosedEvent):
        """持仓关闭：更新风控状态"""
        record = event.trade_record
        if record:
            self.risk.register_trade_result(record.pnl_usd, self.broker.equity)


# ─────────────────────────────────────────────
# 人工控制接口（非自动化命令行操作）
# ─────────────────────────────────────────────

def human_set_regime(system: WTISystem, regime_str: str, reason: str, hours: float = 4.0):
    """
    人工设置市场环境（你的宏观判断接入点）。
    使用方式：在另一个终端或Jupyter中调用。

    示例：
      human_set_regime(sys, "blocked", "中东局势严峻，今日停止交易", 8.0)
      human_set_regime(sys, "trend", "明显单边上行趋势", 2.0)
    """
    regime_map = {
        "normal": Regime.NORMAL,
        "event": Regime.EVENT,
        "trend": Regime.TREND,
        "blocked": Regime.BLOCKED,
    }
    regime = regime_map.get(regime_str.lower())
    if not regime:
        print(f"无效的regime: {regime_str}. 可选: {list(regime_map.keys())}")
        return
    system.regime.set_human_override(regime, reason, hours)
    print(f"✅ 环境已设置为 {regime_str}，有效 {hours} 小时")


def human_kill_switch(system: WTISystem):
    """
    人工紧急停止。不可撤销，需重启程序。
    """
    asyncio.ensure_future(system.bus.publish(KillSwitchEvent("human_manual")))
    print("⚠️  KILL SWITCH 已激活")


# ─────────────────────────────────────────────
# 启动入口
# ─────────────────────────────────────────────

async def main():
    system = WTISystem()
    system.setup()
    await system.start()


if __name__ == "__main__":
    import os
    os.makedirs("logs", exist_ok=True)
    asyncio.run(main())
