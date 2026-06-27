"""
WTI v1 — 事件总线
系统核心通信机制。所有模块通过事件总线交互，不直接相互调用。
好处：更换平台、数据源或策略时，只需修改对应模块，不影响其他部分。
"""

import asyncio
import logging
from collections import defaultdict
from typing import Callable, Any, Dict, List, Type
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 系统事件类型（内部消息，与市场事件区分）
# ─────────────────────────────────────────────

@dataclass
class NewBarEvent:
    """新K线形成"""
    bar: Any  # models.core.Bar


@dataclass
class NewTickEvent:
    """新报价"""
    tick: Any  # models.core.Tick


@dataclass
class MarketEventReceived:
    """收到市场事件（新闻/经济数据）"""
    event: Any  # models.core.MarketEvent


@dataclass
class RegimeChangedEvent:
    """市场环境切换"""
    old_regime: str
    new_regime: str
    reason: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class SignalGeneratedEvent:
    """信号生成"""
    signal: Any  # models.core.Signal


@dataclass
class OrderSubmittedEvent:
    """订单提交"""
    order: Any


@dataclass
class OrderFilledEvent:
    """订单成交"""
    order: Any
    position: Any


@dataclass
class PositionClosedEvent:
    """持仓关闭"""
    position: Any
    trade_record: Any


@dataclass
class RiskHaltEvent:
    """风控停手"""
    reason: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class KillSwitchEvent:
    """人工紧急停止"""
    triggered_by: str = "manual"
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class SystemStartEvent:
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class SystemStopEvent:
    reason: str = "normal_shutdown"
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


# ─────────────────────────────────────────────
# 事件总线实现
# ─────────────────────────────────────────────

class EventBus:
    """
    异步事件总线。
    订阅者注册回调函数，发布者发送事件，总线负责路由。
    所有事件按类型路由，支持多订阅者。
    """

    def __init__(self):
        self._subscribers: Dict[Type, List[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._processed_count = 0

    def subscribe(self, event_type: Type, handler: Callable):
        """
        注册事件处理器。
        handler可以是普通函数或async函数。
        """
        self._subscribers[event_type].append(handler)
        logger.debug(f"[EventBus] 注册处理器: {event_type.__name__} → {handler.__qualname__}")

    def unsubscribe(self, event_type: Type, handler: Callable):
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Any):
        """发布事件到队列（非阻塞）"""
        await self._queue.put(event)

    def publish_sync(self, event: Any):
        """同步发布（用于非async上下文）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._queue.put(event))
            else:
                loop.run_until_complete(self._queue.put(event))
        except RuntimeError:
            # 如果没有事件循环，创建一个
            asyncio.run(self._queue.put(event))

    async def _dispatch(self, event: Any):
        """分发事件给所有订阅者"""
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])

        if not handlers:
            logger.debug(f"[EventBus] 无处理器: {event_type.__name__}")
            return

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"[EventBus] 处理器异常 {handler.__qualname__} "
                    f"处理 {event_type.__name__}: {e}",
                    exc_info=True
                )
                # 不抛出异常，继续处理其他订阅者

        self._processed_count += 1

    async def run(self):
        """启动事件循环（在主任务中运行）"""
        self._running = True
        logger.info("[EventBus] 启动")

        while self._running:
            try:
                # 超时机制：避免永久阻塞
                event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[EventBus] 循环异常: {e}", exc_info=True)

        logger.info(f"[EventBus] 停止，共处理事件: {self._processed_count}")

    async def stop(self):
        """停止事件循环"""
        self._running = False
        # 发送一个哨兵事件打破阻塞
        await self._queue.put(None)


# 全局单例
_bus = EventBus()


def get_bus() -> EventBus:
    """获取全局事件总线实例"""
    return _bus
