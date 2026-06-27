"""
WTI Trading Platform - Trading Engine Services
"""
import logging
import random
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple, Deque
from collections import deque
from dataclasses import dataclass

from models import (
    Regime, Direction, SignalStatus, ExitReason, EventPriority,
    Bar, Tick, Indicators, MarketEvent, Signal, Position, 
    TradeRecord, RiskState, EconomicEvent
)

logger = logging.getLogger(__name__)


# Configuration
@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 0.005
    max_daily_loss_pct: float = 0.015
    max_consecutive_losses: int = 3
    max_spread_ticks: float = 6.0
    max_slippage_ticks: float = 4.0
    data_gap_timeout_sec: int = 30
    account_equity: float = 50000.0


@dataclass
class ConfirmationConfig:
    min_wait_sec: int = 20
    max_wait_sec: int = 90
    breakout_pct_of_range: float = 0.60
    ema_fast: int = 20
    ema_slow: int = 50
    adx_threshold: float = 22.0
    vwap_atr_max_deviation: float = 1.5
    spike_filter_atr_mult: float = 3.0
    min_volume_ratio: float = 1.2
    max_spread_ticks: float = 6.0


@dataclass
class RegimeConfig:
    vol_spike_multiplier: float = 1.8
    atr_baseline_periods: int = 60
    blocked_spread_ticks: float = 10.0
    blocked_vol_multiplier: float = 4.0


# Risk Service
class RiskService:
    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self.state = RiskState()
        self._current_date = datetime.now(timezone.utc).date()
    
    def check_signal(self, signal: Signal, current_tick: Tick, equity: float) -> Tuple[bool, str, int]:
        """Check if signal passes risk controls. Returns (allowed, reason, position_size)"""
        if self.state.kill_switch_active:
            return False, "Kill switch active", 0
        
        if self.state.is_halted:
            return False, f"Risk halt: {self.state.halt_reason}", 0
        
        self._check_day_reset()
        
        daily_loss_pct = abs(min(0, self.state.daily_pnl)) / equity if equity > 0 else 0
        if daily_loss_pct >= self.config.max_daily_loss_pct:
            self._halt(f"Daily loss {daily_loss_pct:.1%} exceeds limit")
            return False, self.state.halt_reason, 0
        
        if self.state.consecutive_losses >= self.config.max_consecutive_losses:
            self._halt(f"Consecutive losses: {self.state.consecutive_losses}")
            return False, self.state.halt_reason, 0
        
        spread_ticks = current_tick.spread / 0.01
        if spread_ticks > self.config.max_spread_ticks:
            return False, f"Spread too wide: {spread_ticks:.1f} ticks", 0
        
        size = self._calc_position_size(signal, equity)
        if size < 1:
            return False, "Position size too small", 0
        
        return True, "Passed", size
    
    def _calc_position_size(self, signal: Signal, equity: float) -> int:
        if signal.entry_price is None or signal.stop_loss_price is None:
            return 0
        
        risk_per_trade = equity * self.config.max_risk_per_trade_pct
        risk_per_contract = abs(signal.entry_price - signal.stop_loss_price) * 1000
        
        if risk_per_contract <= 0:
            return 0
        
        size = int(risk_per_trade / risk_per_contract)
        return max(0, min(size, 5))
    
    def _halt(self, reason: str):
        self.state.is_halted = True
        self.state.halt_reason = reason
        logger.warning(f"[Risk] HALT: {reason}")
    
    def _check_day_reset(self):
        today = datetime.now(timezone.utc).date()
        if today != self._current_date:
            self._current_date = today
            was_killed = self.state.kill_switch_active
            self.state = RiskState()
            self.state.kill_switch_active = was_killed
    
    def activate_kill_switch(self, reason: str = "manual"):
        self.state.kill_switch_active = True
        self.state.is_halted = True
        self.state.halt_reason = f"KILL SWITCH: {reason}"
        logger.critical(f"[Risk] KILL SWITCH activated: {reason}")
    
    def reset_halt(self) -> bool:
        if self.state.kill_switch_active:
            return False
        self.state.is_halted = False
        self.state.halt_reason = ""
        return True
    
    def register_trade_result(self, pnl: float, equity: float):
        self.state.daily_pnl += pnl
        self.state.total_trades_today += 1
        self.state.daily_loss_used_pct = abs(min(0, self.state.daily_pnl)) / equity if equity > 0 else 0
        if pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0


# Regime Service
class RegimeService:
    def __init__(self, config: RegimeConfig = None):
        self.config = config or RegimeConfig()
        self._current_regime: Regime = Regime.NORMAL
        self._regime_entered_at: datetime = datetime.now(timezone.utc)
        self._active_event: Optional[MarketEvent] = None
        self._event_window_end: Optional[datetime] = None
        self._human_override: Optional[Regime] = None
        self._human_override_reason: str = ""
        self._human_override_expiry: Optional[datetime] = None
        self._history: Deque[dict] = deque(maxlen=100)
    
    @property
    def current(self) -> Regime:
        if self._human_override is not None:
            if self._human_override_expiry and datetime.now(timezone.utc) > self._human_override_expiry:
                self._clear_override()
            else:
                return self._human_override
        return self._current_regime
    
    def update(self, indicators: Indicators):
        new_regime = self._evaluate(indicators)
        if new_regime != self._current_regime:
            self._transition(new_regime, indicators)
    
    def on_market_event(self, event: MarketEvent, confirm_window_sec: int):
        if event.priority == EventPriority.C:
            return
        
        self._active_event = event
        self._event_window_end = datetime.now(timezone.utc) + timedelta(seconds=confirm_window_sec)
        self._set_regime(Regime.EVENT, f"Event: {event.headline[:50]}")
    
    def check_event_window_expiry(self):
        if self._current_regime == Regime.EVENT:
            if self._event_window_end and datetime.now(timezone.utc) > self._event_window_end:
                self._active_event = None
                self._event_window_end = None
                self._set_regime(Regime.NORMAL, "Event window expired")
    
    def set_human_override(self, regime: Regime, reason: str, duration_hours: float = 4.0):
        self._human_override = regime
        self._human_override_reason = reason
        self._human_override_expiry = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
        logger.warning(f"[Regime] Human override: {regime.value} - {reason}")
    
    def clear_human_override(self):
        self._clear_override()
    
    def _evaluate(self, ind: Indicators) -> Regime:
        if self._is_blocked(ind):
            return Regime.BLOCKED
        
        if self._current_regime == Regime.EVENT:
            if self._event_window_end and datetime.now(timezone.utc) <= self._event_window_end:
                return Regime.EVENT
        
        if self._is_trend(ind):
            return Regime.TREND
        
        return Regime.NORMAL
    
    def _is_blocked(self, ind: Indicators) -> bool:
        if ind.atr_baseline <= 0:
            return True
        vol_ratio = ind.atr / ind.atr_baseline
        return vol_ratio > self.config.blocked_vol_multiplier
    
    def _is_trend(self, ind: Indicators) -> bool:
        if ind.adx < 28:
            return False
        if ind.atr_baseline > 0 and (ind.atr / ind.atr_baseline) > 3.0:
            return False
        return True
    
    def _transition(self, new_regime: Regime, ind: Indicators):
        self._history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from": self._current_regime.value,
            "to": new_regime.value,
            "adx": round(ind.adx, 2),
            "vol_ratio": round(ind.volatility_ratio, 2),
        })
        self._set_regime(new_regime, f"ADX={ind.adx:.1f}, vol_ratio={ind.volatility_ratio:.2f}")
    
    def _set_regime(self, regime: Regime, reason: str):
        if regime != self._current_regime:
            logger.info(f"[Regime] {self._current_regime.value} -> {regime.value}: {reason}")
        self._current_regime = regime
        self._regime_entered_at = datetime.now(timezone.utc)
    
    def _clear_override(self):
        self._human_override = None
        self._human_override_reason = ""
        self._human_override_expiry = None
    
    @property
    def summary(self) -> dict:
        return {
            "current_regime": self.current.value,
            "auto_regime": self._current_regime.value,
            "human_override": self._human_override.value if self._human_override else None,
            "override_reason": self._human_override_reason,
            "active_event": self._active_event.headline if self._active_event else None,
        }


# Signal Service
class SignalService:
    def __init__(self, config: ConfirmationConfig = None):
        self.config = config or ConfirmationConfig()
        self._pending_signal: Optional[Signal] = None
        self._event_baseline_price: Optional[float] = None
        self._event_high: Optional[float] = None
        self._event_low: Optional[float] = None
        self._confirmation_start: Optional[datetime] = None
        self._recent_bars: Deque[Bar] = deque(maxlen=20)
        self._generated_signals: List[Signal] = []
    
    def on_event(self, event: MarketEvent, current_tick: Tick):
        if event.priority == EventPriority.C:
            return
        
        if self._pending_signal and self._pending_signal.status == SignalStatus.PENDING:
            self._reject_pending("New event interrupted")
        
        self._event_baseline_price = current_tick.mid
        self._event_high = current_tick.ask
        self._event_low = current_tick.bid
        self._confirmation_start = datetime.now(timezone.utc)
    
    def try_confirm(self, tick: Tick, ind: Indicators, regime: Regime, ml_confidence: float = 0.0) -> Optional[Signal]:
        if self._pending_signal is None:
            self._update_price_range(tick)
            if regime == Regime.BLOCKED:
                return None
            return None
        
        if self._pending_signal.status != SignalStatus.PENDING:
            return None
        
        if self._is_confirmation_timeout():
            self._reject_pending("Confirmation timeout")
            return None
        
        self._update_price_range(tick)
        return self._try_confirm(tick, ind, regime, ml_confidence)
    
    def start_confirmation(self, event: MarketEvent, current_price: float, indicators: Indicators):
        sig = Signal()
        sig.trigger_event = event.headline
        sig.status = SignalStatus.PENDING
        self._pending_signal = sig
        self._event_baseline_price = current_price
        self._event_high = current_price + 0.02
        self._event_low = current_price - 0.02
        self._confirmation_start = datetime.now(timezone.utc)
    
    def _try_confirm(self, tick: Tick, ind: Indicators, regime: Regime, ml_confidence: float) -> Optional[Signal]:
        sig = self._pending_signal
        if sig is None:
            return None
        
        elapsed = (datetime.now(timezone.utc) - self._confirmation_start).total_seconds()
        if elapsed < self.config.min_wait_sec:
            return None
        
        direction, breakout_ok = self._check_breakout(tick)
        if not breakout_ok:
            return None
        
        sig.direction = direction
        sig.breakout_confirmed = True
        
        if direction == Direction.LONG:
            sig.ema_aligned = ind.ema_fast > ind.ema_slow
        else:
            sig.ema_aligned = ind.ema_fast < ind.ema_slow
        
        sig.adx_confirmed = ind.adx >= self.config.adx_threshold
        sig.volume_confirmed = ind.volume_ratio >= self.config.min_volume_ratio
        
        if direction == Direction.LONG:
            vwap_deviation = (tick.mid - ind.vwap) / ind.atr if ind.atr > 0 else 0
        else:
            vwap_deviation = (ind.vwap - tick.mid) / ind.atr if ind.atr > 0 else 0
        sig.vwap_ok = vwap_deviation <= self.config.vwap_atr_max_deviation
        
        spread_ticks = tick.spread / 0.01
        sig.spread_ok = spread_ticks <= self.config.max_spread_ticks
        
        all_confirmed = all([
            sig.ema_aligned, sig.adx_confirmed, sig.volume_confirmed,
            sig.vwap_ok, sig.spread_ok, sig.breakout_confirmed
        ])
        
        if all_confirmed or ml_confidence > 0.75:
            sig.entry_price = tick.ask if direction == Direction.LONG else tick.bid
            sig.stop_loss_price = self._calc_stop(direction, sig.entry_price, ind)
            sig.status = SignalStatus.ACCEPTED
            sig.trigger_regime = regime
            sig.confidence_score = ml_confidence
            self._generated_signals.append(sig)
            self._pending_signal = None
            logger.info(f"[Signal] CONFIRMED: {direction.value} @ {sig.entry_price:.2f}")
            return sig
        
        return None
    
    def _check_breakout(self, tick: Tick) -> Tuple[Optional[Direction], bool]:
        if not all([self._event_high, self._event_low, self._event_baseline_price]):
            return None, False
        
        range_size = self._event_high - self._event_low
        if range_size <= 0:
            return None, False
        
        min_breakout = range_size * self.config.breakout_pct_of_range
        
        if tick.ask > self._event_high + min_breakout:
            return Direction.LONG, True
        
        if tick.bid < self._event_low - min_breakout:
            return Direction.SHORT, True
        
        return None, False
    
    def _calc_stop(self, direction: Direction, entry_price: float, ind: Indicators) -> float:
        stop_distance = ind.atr * 1.5
        
        if direction == Direction.LONG:
            return round(entry_price - stop_distance, 2)
        else:
            return round(entry_price + stop_distance, 2)
    
    def _update_price_range(self, tick: Tick):
        if self._event_high is not None:
            self._event_high = max(self._event_high, tick.ask)
        if self._event_low is not None:
            self._event_low = min(self._event_low, tick.bid)
    
    def _is_confirmation_timeout(self) -> bool:
        if not self._confirmation_start:
            return False
        elapsed = (datetime.now(timezone.utc) - self._confirmation_start).total_seconds()
        return elapsed > self.config.max_wait_sec
    
    def _reject_pending(self, reason: str):
        if self._pending_signal:
            self._pending_signal.status = SignalStatus.REJECTED
            self._pending_signal.reject_reason = reason
            self._generated_signals.append(self._pending_signal)
            self._pending_signal = None
            self._reset_event_state()
    
    def _reset_event_state(self):
        self._event_baseline_price = None
        self._event_high = None
        self._event_low = None
        self._confirmation_start = None


# Paper Broker
class PaperBroker:
    def __init__(self, initial_equity: float = 50000.0, slippage_ticks: float = 1.0, commission_per_rt: float = 4.0):
        self.equity = initial_equity
        self.initial_equity = initial_equity
        self.slippage_ticks = slippage_ticks
        self.commission_per_rt = commission_per_rt
        self._positions: Dict[str, Position] = {}
        self._trade_records: List[TradeRecord] = []
        self._current_tick: Optional[Tick] = None
    
    def update_tick(self, tick: Tick):
        self._current_tick = tick
        self._check_stop_losses(tick)
        self._update_unrealized_pnl(tick)
    
    def _update_unrealized_pnl(self, tick: Tick):
        for pos in self.open_positions:
            pos.current_price = tick.mid
            if pos.direction == Direction.LONG:
                pos.unrealized_pnl = (tick.mid - pos.entry_price) * pos.quantity * 1000
            else:
                pos.unrealized_pnl = (pos.entry_price - tick.mid) * pos.quantity * 1000
    
    def submit_order(self, signal: Signal, size: int) -> Optional[Position]:
        if self._current_tick is None:
            return None
        
        fill_price = self._simulate_fill_price(signal.direction)
        
        pos = Position(
            symbol=signal.symbol,
            direction=signal.direction,
            quantity=size,
            entry_price=fill_price,
            stop_loss_price=signal.stop_loss_price,
            signal_id=signal.id,
            current_price=fill_price,
        )
        self._positions[pos.id] = pos
        logger.info(f"[Broker] OPEN: {pos.direction.value} {size}x @ {fill_price:.2f}")
        return pos
    
    def close_position(self, position_id: str, reason: ExitReason) -> Optional[TradeRecord]:
        pos = self._positions.get(position_id)
        if not pos or not pos.is_open:
            return None
        
        if self._current_tick is None:
            return None
        
        if pos.direction == Direction.LONG:
            exit_price = self._current_tick.bid - (self.slippage_ticks * 0.01)
        else:
            exit_price = self._current_tick.ask + (self.slippage_ticks * 0.01)
        
        pos.exit_price = round(exit_price, 2)
        pos.exit_reason = reason
        pos.closed_at = datetime.now(timezone.utc)
        pos.is_open = False
        
        if pos.direction == Direction.LONG:
            raw_pnl = (pos.exit_price - pos.entry_price) * pos.quantity * 1000
        else:
            raw_pnl = (pos.entry_price - pos.exit_price) * pos.quantity * 1000
        
        commission = self.commission_per_rt * pos.quantity
        net_pnl = raw_pnl - commission
        self.equity += net_pnl
        
        hold_minutes = (pos.closed_at - pos.opened_at).total_seconds() / 60
        
        record = TradeRecord(
            date=pos.opened_at.strftime("%Y-%m-%d"),
            symbol=pos.symbol,
            direction=pos.direction.value,
            entry_price=pos.entry_price,
            exit_price=pos.exit_price,
            quantity=pos.quantity,
            pnl_usd=round(net_pnl, 2),
            hold_minutes=round(hold_minutes, 1),
            exit_reason=reason.value,
        )
        self._trade_records.append(record)
        
        logger.info(f"[Broker] CLOSE: {pos.direction.value} @ {pos.exit_price:.2f} PnL={net_pnl:+.2f}")
        return record

    def partial_close_position(self, position_id: str, close_pct: float = 0.5) -> Optional[TradeRecord]:
        """
        Partially close a position (e.g. 50% at TP1).
        Reduces the position quantity and books partial P&L.
        """
        pos = self._positions.get(position_id)
        if not pos or not pos.is_open or self._current_tick is None:
            return None

        close_qty = max(1, int(pos.quantity * close_pct))
        if close_qty >= pos.quantity:
            return self.close_position(position_id, ExitReason.PARTIAL_PROFIT)

        if pos.direction == Direction.LONG:
            exit_price = self._current_tick.bid - (self.slippage_ticks * 0.01)
            raw_pnl = (exit_price - pos.entry_price) * close_qty * 1000
        else:
            exit_price = self._current_tick.ask + (self.slippage_ticks * 0.01)
            raw_pnl = (pos.entry_price - exit_price) * close_qty * 1000

        commission = self.commission_per_rt * close_qty
        net_pnl = raw_pnl - commission
        self.equity += net_pnl
        pos.quantity -= close_qty

        hold_minutes = (datetime.now(timezone.utc) - pos.opened_at).total_seconds() / 60

        record = TradeRecord(
            date=pos.opened_at.strftime("%Y-%m-%d"),
            symbol=pos.symbol,
            direction=pos.direction.value,
            entry_price=pos.entry_price,
            exit_price=round(exit_price, 2),
            quantity=close_qty,
            pnl_usd=round(net_pnl, 2),
            hold_minutes=round(hold_minutes, 1),
            exit_reason=ExitReason.PARTIAL_PROFIT.value,
        )
        self._trade_records.append(record)

        logger.info(f"[Broker] PARTIAL CLOSE: {pos.direction.value} {close_qty}x @ {exit_price:.2f} PnL={net_pnl:+.2f} | Remaining: {pos.quantity}")
        return record

    def check_take_profits(self, take_profit_levels: Dict[str, Dict]):
        """
        Check take-profit levels for all open positions.
        take_profit_levels: {position_id: {"tp1": price, "tp2": price, "tp1_hit": bool}}
        Returns list of (position_id, tp_level, record) for triggered TPs.
        """
        if self._current_tick is None:
            return []

        triggered = []
        for pos in self.open_positions:
            tp_info = take_profit_levels.get(pos.id)
            if not tp_info:
                continue

            current_mid = self._current_tick.mid

            # Check TP1 (partial close 50%)
            if not tp_info.get("tp1_hit", False):
                tp1 = tp_info.get("tp1", 0)
                if tp1 > 0:
                    hit = (pos.direction == Direction.LONG and current_mid >= tp1) or \
                          (pos.direction == Direction.SHORT and current_mid <= tp1)
                    if hit:
                        record = self.partial_close_position(pos.id, 0.5)
                        if record:
                            tp_info["tp1_hit"] = True
                            triggered.append((pos.id, "tp1", record))
                            # Move stop loss to breakeven
                            pos.stop_loss_price = pos.entry_price
                            logger.info(f"[Broker] TP1 HIT: Partial close 50%, SL moved to breakeven")

            # Check TP2 (close remaining)
            if tp_info.get("tp1_hit", False):
                tp2 = tp_info.get("tp2", 0)
                if tp2 > 0:
                    hit = (pos.direction == Direction.LONG and current_mid >= tp2) or \
                          (pos.direction == Direction.SHORT and current_mid <= tp2)
                    if hit:
                        record = self.close_position(pos.id, ExitReason.PARTIAL_PROFIT)
                        if record:
                            triggered.append((pos.id, "tp2", record))
                            logger.info(f"[Broker] TP2 HIT: Full close remaining")

        return triggered
    
    @property
    def open_positions(self) -> List[Position]:
        return [p for p in self._positions.values() if p.is_open]
    
    @property
    def trade_records(self) -> List[TradeRecord]:
        return self._trade_records
    
    def _simulate_fill_price(self, direction: Direction) -> float:
        if self._current_tick is None:
            return 0.0
        
        slippage = self.slippage_ticks * 0.01
        actual_slippage = slippage * random.uniform(0.5, 1.5)
        
        if direction == Direction.LONG:
            return round(self._current_tick.ask + actual_slippage, 2)
        else:
            return round(self._current_tick.bid - actual_slippage, 2)
    
    def _check_stop_losses(self, tick: Tick):
        for pos in self.open_positions:
            hit = False
            if pos.direction == Direction.LONG and tick.bid <= pos.stop_loss_price:
                hit = True
            elif pos.direction == Direction.SHORT and tick.ask >= pos.stop_loss_price:
                hit = True
            
            if hit:
                logger.warning(f"[Broker] STOP LOSS: {pos.direction.value} @ {pos.stop_loss_price:.2f}")
                self.close_position(pos.id, ExitReason.STOP_LOSS)
    
    def get_summary(self) -> dict:
        records = self._trade_records
        if not records:
            return {"message": "No trades"}
        
        wins = [r for r in records if r.pnl_usd > 0]
        losses = [r for r in records if r.pnl_usd <= 0]
        total_pnl = sum(r.pnl_usd for r in records)
        
        return {
            "total_trades": len(records),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(records) if records else 0,
            "total_pnl": total_pnl,
            "avg_win": sum(r.pnl_usd for r in wins) / len(wins) if wins else 0,
            "avg_loss": sum(r.pnl_usd for r in losses) / len(losses) if losses else 0,
            "equity": self.equity,
            "return_pct": (self.equity - self.initial_equity) / self.initial_equity,
        }


# Market Data Generator
class MarketDataGenerator:
    """Generates realistic WTI price data for simulation"""
    
    def __init__(self, initial_price: float = 75.0):
        self.current_price = initial_price
        self.volatility = 0.002
        self.drift = 0.0
        self._bars: List[Bar] = []
        self._last_bar_time: Optional[datetime] = None
    
    def generate_tick(self) -> Tick:
        change = random.gauss(self.drift, self.volatility) * self.current_price
        self.current_price = max(50, min(120, self.current_price + change))
        
        spread = random.uniform(0.02, 0.06)
        bid = self.current_price - spread / 2
        ask = self.current_price + spread / 2
        
        return Tick(
            timestamp=datetime.now(timezone.utc),
            bid=round(bid, 2),
            ask=round(ask, 2),
            last=round(self.current_price, 2),
            volume=random.randint(100, 1000),
        )
    
    def generate_bar(self, timeframe_minutes: int = 1) -> Bar:
        now = datetime.now(timezone.utc)
        
        open_price = self.current_price
        changes = [random.gauss(0, self.volatility) * open_price for _ in range(10)]
        prices = [open_price]
        for c in changes:
            prices.append(max(50, min(120, prices[-1] + c)))
        
        self.current_price = prices[-1]
        
        bar = Bar(
            timestamp=now,
            open=round(open_price, 2),
            high=round(max(prices), 2),
            low=round(min(prices), 2),
            close=round(self.current_price, 2),
            volume=random.randint(5000, 50000),
        )
        self._bars.append(bar)
        return bar
    
    def generate_indicators(self, bars: List[Bar] = None) -> Indicators:
        if bars is None:
            bars = self._bars[-60:] if len(self._bars) >= 60 else self._bars
        
        if not bars:
            bars = [self.generate_bar() for _ in range(20)]
        
        closes = [b.close for b in bars]
        
        ema_fast = self._ema(closes, 20)
        ema_slow = self._ema(closes, 50) if len(closes) >= 50 else ema_fast * 0.99
        
        atr = self._atr(bars, 14)
        atr_baseline = self._atr(bars, min(60, len(bars)))
        
        adx = 20 + random.uniform(-5, 15)
        vwap = sum(b.close * b.volume for b in bars[-20:]) / max(1, sum(b.volume for b in bars[-20:]))
        
        avg_vol = sum(b.volume for b in bars[-20:]) / max(1, len(bars[-20:]))
        current_vol = bars[-1].volume if bars else 10000
        volume_ratio = current_vol / max(1, avg_vol)
        
        volatility_ratio = atr / max(0.01, atr_baseline)
        
        return Indicators(
            timestamp=datetime.now(timezone.utc),
            ema_fast=round(ema_fast, 2),
            ema_slow=round(ema_slow, 2),
            adx=round(adx, 2),
            atr=round(atr, 4),
            atr_baseline=round(atr_baseline, 4),
            vwap=round(vwap, 2),
            volume_ratio=round(volume_ratio, 2),
            volatility_ratio=round(volatility_ratio, 2),
        )
    
    def _ema(self, prices: List[float], period: int) -> float:
        if not prices:
            return 0
        if len(prices) < period:
            return sum(prices) / len(prices)
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def _atr(self, bars: List[Bar], period: int) -> float:
        if len(bars) < 2:
            return 0.5
        
        trs = []
        for i in range(1, min(period + 1, len(bars))):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        
        return sum(trs) / len(trs) if trs else 0.5
    
    def set_volatility(self, vol_level: str):
        levels = {"low": 0.001, "normal": 0.002, "high": 0.004, "extreme": 0.008}
        self.volatility = levels.get(vol_level, 0.002)
    
    def set_trend(self, direction: str):
        trends = {"up": 0.0002, "down": -0.0002, "neutral": 0}
        self.drift = trends.get(direction, 0)


# Economic Calendar Service
class EconomicCalendarService:
    """Generates realistic economic events"""
    
    def __init__(self):
        self._events: List[EconomicEvent] = []
        self._generate_initial_events()
    
    def _generate_initial_events(self):
        now = datetime.now(timezone.utc)
        
        event_templates = [
            ("EIA Crude Oil Inventories", "United States", "high", "EIA"),
            ("API Weekly Crude Oil Stock", "United States", "medium", "API"),
            ("OPEC+ Meeting", "OPEC", "high", "OPEC"),
            ("US Non-Farm Payrolls", "United States", "high", "NFP"),
            ("Fed Interest Rate Decision", "United States", "high", "FED"),
            ("China PMI", "China", "medium", "PMI"),
            ("US CPI YoY", "United States", "high", "CPI"),
            ("OPEC Monthly Report", "OPEC", "medium", "OPEC"),
        ]
        
        for i, (name, country, importance, event_type) in enumerate(event_templates):
            days_offset = random.randint(0, 14)
            hours_offset = random.randint(8, 18)
            
            event = EconomicEvent(
                event_name=name,
                country=country,
                date=now + timedelta(days=days_offset, hours=hours_offset),
                importance=importance,
                forecast=random.uniform(-2, 2) if "inventory" in name.lower() else None,
                previous=random.uniform(-3, 3) if "inventory" in name.lower() else None,
                event_type=event_type,
            )
            self._events.append(event)
        
        self._events.sort(key=lambda e: e.date)
    
    def get_upcoming_events(self, days: int = 7) -> List[EconomicEvent]:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)
        return [e for e in self._events if now <= e.date <= cutoff]
    
    def get_events_by_type(self, event_type: str) -> List[EconomicEvent]:
        return [e for e in self._events if e.event_type == event_type]
    
    def trigger_event(self, event_id: str) -> Optional[MarketEvent]:
        for event in self._events:
            if event.id == event_id:
                # Generate actual value
                if event.forecast is not None:
                    actual = event.forecast + random.uniform(-2, 2)
                else:
                    actual = random.uniform(-3, 3)
                event.actual = round(actual, 2)
                
                # Calculate surprise
                surprise = 0.0
                if event.forecast is not None and event.forecast != 0:
                    surprise = (actual - event.forecast) / abs(event.forecast)
                
                priority = EventPriority.A if event.importance == "high" else EventPriority.B
                
                # Format headline
                if event.forecast is not None:
                    headline = f"{event.event_name}: Actual {actual:.2f} vs Forecast {event.forecast:.2f}"
                else:
                    headline = f"{event.event_name}: Actual {actual:.2f}"
                
                return MarketEvent(
                    event_type=event.event_type,
                    priority=priority,
                    headline=headline,
                    actual_value=actual,
                    forecast_value=event.forecast,
                    surprise_pct=surprise,
                    raw_source="economic_calendar",
                )
        return None
