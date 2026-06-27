"""
WTI Trading Platform - Backtest Engine
"""
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import math

from models import (
    Bar, Tick, Indicators, MarketEvent, EventPriority, Regime, Direction,
    Signal, SignalStatus, TradeRecord, Position, ExitReason,
    BacktestConfig, BacktestResult, EconomicEvent
)
from trading_engine import (
    RiskService, RegimeService, SignalService, PaperBroker,
    MarketDataGenerator, RiskConfig, ConfirmationConfig, RegimeConfig
)

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Historical backtesting engine for WTI trading strategy"""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.regime_svc = RegimeService()
        self.signal_svc = SignalService()
        self.risk_svc = RiskService(RiskConfig(account_equity=config.initial_equity))
        self.broker = PaperBroker(
            initial_equity=config.initial_equity,
            slippage_ticks=config.slippage_ticks,
            commission_per_rt=config.commission_per_rt,
        )
    
    def run(
        self,
        bars: List[Bar],
        events: List[MarketEvent],
    ) -> BacktestResult:
        """Execute backtest on historical data"""
        
        logger.info(f"[Backtest] Starting: {len(bars)} bars, {len(events)} events")
        
        equity_curve = []
        event_idx = 0
        
        for i, bar in enumerate(bars):
            # Generate indicators from historical bars
            historical_bars = bars[max(0, i-60):i+1]
            indicators = self._calculate_indicators(historical_bars)
            
            # Check for events
            while event_idx < len(events) and events[event_idx].timestamp <= bar.timestamp:
                evt = events[event_idx]
                if evt.priority in [EventPriority.A, EventPriority.B]:
                    self.regime_svc.on_market_event(evt, 60)
                    fake_tick = Tick(
                        timestamp=bar.timestamp,
                        bid=bar.close - 0.02,
                        ask=bar.close + 0.02,
                        last=bar.close,
                        volume=bar.volume,
                    )
                    self.signal_svc.on_event(evt, fake_tick)
                    self.signal_svc.start_confirmation(evt, bar.close, indicators)
                event_idx += 1
            
            # Update regime
            self.regime_svc.update(indicators)
            self.regime_svc.check_event_window_expiry()
            current_regime = self.regime_svc.current
            
            # Create tick from bar
            tick = Tick(
                timestamp=bar.timestamp,
                bid=bar.close - 0.02,
                ask=bar.close + 0.02,
                last=bar.close,
                volume=bar.volume,
            )
            self.broker.update_tick(tick)
            
            # Check for time-based exits
            for pos in self.broker.open_positions:
                hold_time = (bar.timestamp - pos.opened_at).total_seconds() / 60
                if hold_time > 45:  # Max hold time
                    self.broker.close_position(pos.id, ExitReason.TIME_EXIT)
                    self.risk_svc.register_trade_result(
                        self.broker.trade_records[-1].pnl_usd if self.broker.trade_records else 0,
                        self.broker.equity
                    )
            
            # Try to confirm signals
            signal = self.signal_svc.try_confirm(tick, indicators, current_regime, 0.6)
            if signal and signal.status == SignalStatus.ACCEPTED:
                check_result = self.risk_svc.check_signal(signal, tick, self.broker.equity)
                if check_result[0]:  # allowed
                    self.broker.submit_order(signal, check_result[2])
            
            # Record equity curve
            if i % 10 == 0:
                equity_curve.append({
                    "timestamp": bar.timestamp.isoformat(),
                    "equity": self.broker.equity,
                    "price": bar.close,
                })
        
        # Close remaining positions
        for pos in self.broker.open_positions:
            self.broker.close_position(pos.id, ExitReason.TIME_EXIT)
        
        # Calculate metrics
        result = self._calculate_metrics(equity_curve)
        logger.info(f"[Backtest] Complete: {result.total_trades} trades, {result.win_rate:.1%} win rate")
        
        return result
    
    def _calculate_indicators(self, bars: List[Bar]) -> Indicators:
        """Calculate technical indicators from bars"""
        if not bars:
            return Indicators(
                timestamp=datetime.now(timezone.utc),
                ema_fast=75.0,
                ema_slow=75.0,
                adx=20.0,
                atr=0.5,
                atr_baseline=0.5,
                vwap=75.0,
                volume_ratio=1.0,
                volatility_ratio=1.0,
            )
        
        closes = [b.close for b in bars]
        
        # EMA calculations
        ema_fast = self._ema(closes, min(20, len(closes)))
        ema_slow = self._ema(closes, min(50, len(closes)))
        
        # ATR calculation
        atr = self._atr(bars, min(14, len(bars)))
        atr_baseline = self._atr(bars, min(60, len(bars)))
        
        # ADX approximation (simplified)
        adx = self._approximate_adx(bars)
        
        # VWAP
        vwap = sum(b.close * b.volume for b in bars[-20:]) / max(1, sum(b.volume for b in bars[-20:]))
        
        # Volume ratio
        if len(bars) >= 20:
            avg_vol = sum(b.volume for b in bars[-20:]) / 20
            volume_ratio = bars[-1].volume / max(1, avg_vol)
        else:
            volume_ratio = 1.0
        
        return Indicators(
            timestamp=bars[-1].timestamp,
            ema_fast=round(ema_fast, 2),
            ema_slow=round(ema_slow, 2),
            adx=round(adx, 2),
            atr=round(atr, 4),
            atr_baseline=round(atr_baseline, 4),
            vwap=round(vwap, 2),
            volume_ratio=round(volume_ratio, 2),
            volatility_ratio=round(atr / max(0.01, atr_baseline), 2),
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
    
    def _approximate_adx(self, bars: List[Bar]) -> float:
        """Simplified ADX approximation"""
        if len(bars) < 14:
            return 20.0
        
        # Calculate directional movement
        plus_dm = []
        minus_dm = []
        tr_list = []
        
        for i in range(1, min(15, len(bars))):
            high_diff = bars[i].high - bars[i-1].high
            low_diff = bars[i-1].low - bars[i].low
            
            plus_dm.append(max(0, high_diff) if high_diff > low_diff else 0)
            minus_dm.append(max(0, low_diff) if low_diff > high_diff else 0)
            
            tr = max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - bars[i-1].close),
                abs(bars[i].low - bars[i-1].close)
            )
            tr_list.append(tr)
        
        if not tr_list or sum(tr_list) == 0:
            return 20.0
        
        plus_di = 100 * sum(plus_dm) / sum(tr_list)
        minus_di = 100 * sum(minus_dm) / sum(tr_list)
        
        di_sum = plus_di + minus_di
        if di_sum == 0:
            return 20.0
        
        dx = 100 * abs(plus_di - minus_di) / di_sum
        return min(60, max(10, dx))
    
    def _calculate_metrics(self, equity_curve: List[Dict[str, Any]]) -> BacktestResult:
        """Calculate backtest performance metrics"""
        records = self.broker.trade_records
        
        total_trades = len(records)
        wins = [r for r in records if r.pnl_usd > 0]
        losses = [r for r in records if r.pnl_usd <= 0]
        
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        
        total_wins = sum(r.pnl_usd for r in wins)
        total_losses = abs(sum(r.pnl_usd for r in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Max drawdown
        max_drawdown = 0
        peak = self.config.initial_equity
        for point in equity_curve:
            equity = point["equity"]
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            max_drawdown = max(max_drawdown, dd)
        
        # Sharpe ratio (simplified)
        returns = []
        for i in range(1, len(equity_curve)):
            prev_eq = equity_curve[i-1]["equity"]
            curr_eq = equity_curve[i]["equity"]
            if prev_eq > 0:
                returns.append((curr_eq - prev_eq) / prev_eq)
        
        if returns:
            avg_return = sum(returns) / len(returns)
            std_return = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns))
            sharpe_ratio = (avg_return / std_return) * math.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        return BacktestResult(
            config=self.config,
            trade_records=[r.model_dump() for r in records],
            equity_curve=equity_curve,
            final_equity=self.broker.equity,
            total_trades=total_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
        )


def generate_historical_data(
    start_date: str,
    end_date: str,
    include_events: bool = True,
) -> tuple[List[Bar], List[MarketEvent]]:
    """Generate synthetic historical data for backtesting"""
    
    start = datetime.fromisoformat(start_date + "T00:00:00+00:00")
    end = datetime.fromisoformat(end_date + "T23:59:59+00:00")
    
    generator = MarketDataGenerator(initial_price=75.0)
    bars = []
    events = []
    
    current = start
    while current <= end:
        # Skip weekends
        if current.weekday() < 5:
            # Generate bars for trading hours (roughly 23 hours for futures)
            for hour in range(24):
                for minute in range(0, 60, 5):  # 5-minute bars
                    bar_time = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if bar_time > end:
                        break
                    
                    # Simulate volatility spikes
                    if random.random() < 0.02:
                        generator.set_volatility("high")
                    elif random.random() < 0.01:
                        generator.set_volatility("extreme")
                    else:
                        generator.set_volatility("normal")
                    
                    # Simulate trend changes
                    if random.random() < 0.05:
                        generator.set_trend(random.choice(["up", "down", "neutral"]))
                    
                    bar = generator.generate_bar(5)
                    bar.timestamp = bar_time
                    bars.append(bar)
        
        current += timedelta(days=1)
    
    # Generate random events
    if include_events:
        event_types = [
            ("EIA Crude Oil Inventories", EventPriority.A, "EIA"),
            ("API Weekly Crude Stock", EventPriority.B, "API"),
            ("OPEC+ Meeting Decision", EventPriority.A, "OPEC"),
            ("Fed Rate Decision", EventPriority.B, "FED"),
            ("Middle East Tensions", EventPriority.A, "GEO"),
        ]
        
        num_events = len(bars) // 500  # Roughly one event per 500 bars
        for _ in range(num_events):
            event_template = random.choice(event_types)
            event_bar = random.choice(bars)
            
            actual = random.uniform(-3, 3)
            forecast = actual + random.uniform(-1, 1)
            
            event = MarketEvent(
                timestamp=event_bar.timestamp,
                event_type=event_template[2],
                priority=event_template[1],
                headline=f"{event_template[0]}: {actual:+.2f}M barrels",
                actual_value=actual,
                forecast_value=forecast,
                surprise_pct=(actual - forecast) / abs(forecast) if forecast != 0 else 0,
                raw_source="historical_simulation",
            )
            events.append(event)
        
        events.sort(key=lambda e: e.timestamp)
    
    return bars, events
