"""
WTI Trading Platform - Strategy Replay Engine
Simulates historical events and replays market conditions.
Includes bot strategy simulation for hypothetical PnL analysis.
"""
import logging
import math
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Pre-defined historical oil market events for replay
HISTORICAL_EVENTS = {
    "hormuz_2024": {
        "name": "Strait of Hormuz Tension (2024)",
        "description": "Houthi attacks on Red Sea shipping, oil tanker disruption fears",
        "date": "2024-01-15",
        "duration_bars": 60,
        "initial_price": 72.5,
        "price_trajectory": "spike_up",
        "max_move_pct": 8.5,
        "volatility_mult": 3.0,
        "regime_sequence": ["normal", "event", "spike", "event", "normal"],
    },
    "opec_cut_2023": {
        "name": "OPEC+ Surprise Production Cut (2023)",
        "description": "OPEC+ announced unexpected 1.16M bpd production cut",
        "date": "2023-04-02",
        "duration_bars": 80,
        "initial_price": 75.0,
        "price_trajectory": "rally",
        "max_move_pct": 6.0,
        "volatility_mult": 2.0,
        "regime_sequence": ["normal", "event", "normal", "normal"],
    },
    "svb_2023": {
        "name": "SVB Bank Crisis (2023)",
        "description": "Silicon Valley Bank collapse triggers risk-off, oil plunges on demand fears",
        "date": "2023-03-10",
        "duration_bars": 100,
        "initial_price": 77.5,
        "price_trajectory": "crash",
        "max_move_pct": -12.0,
        "volatility_mult": 2.5,
        "regime_sequence": ["normal", "spike", "event", "spike", "normal"],
    },
    "russia_ukraine_2022": {
        "name": "Russia-Ukraine Invasion (2022)",
        "description": "Russian invasion of Ukraine, oil spikes to $130",
        "date": "2022-02-24",
        "duration_bars": 120,
        "initial_price": 92.0,
        "price_trajectory": "mega_spike",
        "max_move_pct": 42.0,
        "volatility_mult": 4.0,
        "regime_sequence": ["normal", "event", "spike", "spike", "event", "spike", "event", "normal"],
    },
    "covid_crash_2020": {
        "name": "COVID-19 Oil Crash (2020)",
        "description": "Global lockdowns + Saudi-Russia price war, oil goes negative",
        "date": "2020-03-09",
        "duration_bars": 150,
        "initial_price": 41.0,
        "price_trajectory": "mega_crash",
        "max_move_pct": -65.0,
        "volatility_mult": 5.0,
        "regime_sequence": ["normal", "event", "spike", "blocked", "spike", "blocked", "spike", "event", "normal"],
    },
    "eia_surprise_draw": {
        "name": "EIA Surprise Inventory Draw",
        "description": "Weekly EIA report shows unexpected 10M barrel draw",
        "date": "2025-06-15",
        "duration_bars": 30,
        "initial_price": 73.0,
        "price_trajectory": "spike_up",
        "max_move_pct": 3.5,
        "volatility_mult": 1.8,
        "regime_sequence": ["normal", "event", "normal"],
    },
    "fed_hawkish_2024": {
        "name": "Fed Hawkish Surprise (2024)",
        "description": "Fed signals more rate hikes, USD surges, oil drops",
        "date": "2024-09-20",
        "duration_bars": 40,
        "initial_price": 70.0,
        "price_trajectory": "selloff",
        "max_move_pct": -5.0,
        "volatility_mult": 1.5,
        "regime_sequence": ["normal", "event", "normal"],
    },
    "china_stimulus_2024": {
        "name": "China Major Stimulus (2024)",
        "description": "China announces massive economic stimulus, oil demand outlook improves",
        "date": "2024-09-24",
        "duration_bars": 50,
        "initial_price": 68.0,
        "price_trajectory": "rally",
        "max_move_pct": 7.0,
        "volatility_mult": 1.8,
        "regime_sequence": ["normal", "event", "normal", "normal"],
    },
}


def _generate_trajectory(event: Dict) -> List[Dict]:
    """Generate price bars for a historical event replay"""
    bars = []
    price = event["initial_price"]
    n = event["duration_bars"]
    max_move = event["max_move_pct"] / 100 * price
    trajectory = event["price_trajectory"]
    vol_mult = event["volatility_mult"]
    regimes = event["regime_sequence"]
    base_vol = 0.003

    for i in range(n):
        t = i / n  # Progress 0→1
        regime_idx = min(int(t * len(regimes)), len(regimes) - 1)
        regime = regimes[regime_idx]

        # Trajectory shape
        if trajectory == "spike_up":
            drift = max_move * math.exp(-((t - 0.3) ** 2) / 0.05) * 0.04
        elif trajectory == "rally":
            drift = max_move / n * (1 + math.sin(t * math.pi))
        elif trajectory == "crash":
            drift = max_move / n * (1 + 2 * t)
        elif trajectory == "mega_spike":
            drift = max_move / n * math.exp(-((t - 0.25) ** 2) / 0.1) * 3
        elif trajectory == "mega_crash":
            drift = max_move / n * (1 + 3 * t)
        elif trajectory == "selloff":
            drift = max_move / n * (1 + t)
        else:
            drift = max_move / n

        # Apply regime-based volatility
        regime_vol = {"normal": 1.0, "event": 2.0, "spike": 3.0, "blocked": 4.0}.get(regime, 1.0)
        vol = base_vol * vol_mult * regime_vol

        change = drift + random.gauss(0, vol) * price
        price = max(5.0, price + change)

        spread = 0.03 * regime_vol * vol_mult
        adx = 15 + random.uniform(0, 30) * (1 + vol_mult * 0.2)
        atr = abs(change) * random.uniform(1.5, 3.0) + 0.1

        bars.append({
            "bar": i + 1,
            "time_offset_min": i * 5,
            "price": round(price, 2),
            "change_pct": round((price - event["initial_price"]) / event["initial_price"] * 100, 2),
            "spread": round(spread, 4),
            "regime": regime,
            "adx": round(min(60, adx), 1),
            "atr": round(atr, 3),
            "vol_ratio": round(vol_mult * regime_vol * random.uniform(0.8, 1.2), 2),
            "fragility_score": round(min(100, regime_vol * vol_mult * 15 + random.uniform(0, 20)), 1),
        })

    return bars


class ReplayEngine:
    """Replay historical events to test strategies"""

    def get_events_list(self) -> List[Dict]:
        """Get list of available historical events"""
        return [
            {
                "id": eid,
                "name": e["name"],
                "description": e["description"],
                "date": e["date"],
                "initial_price": e["initial_price"],
                "max_move_pct": e["max_move_pct"],
                "duration_bars": e["duration_bars"],
                "trajectory": e["price_trajectory"],
            }
            for eid, e in HISTORICAL_EVENTS.items()
        ]

    def replay_event(self, event_id: str) -> Dict:
        """Replay a historical event, returning full price trajectory and analytics"""
        event = HISTORICAL_EVENTS.get(event_id)
        if not event:
            return {"error": "Event not found"}

        bars = _generate_trajectory(event)

        # Analytics
        prices = [b["price"] for b in bars]
        max_price = max(prices)
        min_price = min(prices)
        final_price = prices[-1]
        total_return_pct = (final_price - event["initial_price"]) / event["initial_price"] * 100

        max_drawdown = 0
        peak = prices[0]
        for p in prices:
            if p > peak:
                peak = p
            dd = (peak - p) / peak * 100
            if dd > max_drawdown:
                max_drawdown = dd

        regime_distribution = {}
        for b in bars:
            r = b["regime"]
            regime_distribution[r] = regime_distribution.get(r, 0) + 1

        avg_fragility = sum(b["fragility_score"] for b in bars) / len(bars)

        return {
            "event": {
                "id": event_id,
                "name": event["name"],
                "description": event["description"],
                "date": event["date"],
                "trajectory": event["price_trajectory"],
            },
            "bars": bars,
            "analytics": {
                "initial_price": event["initial_price"],
                "final_price": round(final_price, 2),
                "max_price": round(max_price, 2),
                "min_price": round(min_price, 2),
                "total_return_pct": round(total_return_pct, 2),
                "max_drawdown_pct": round(max_drawdown, 2),
                "avg_fragility": round(avg_fragility, 1),
                "duration_bars": len(bars),
                "regime_distribution": regime_distribution,
            },
        }


    def simulate_strategy(self, event_id: str, config: Optional[Dict] = None) -> Dict:
        """
        Simulate the trading bot strategy on a historical event.
        Runs through each bar, computes signals, and generates hypothetical trades with PnL.
        """
        event = HISTORICAL_EVENTS.get(event_id)
        if not event:
            return {"error": "Event not found"}

        bars = _generate_trajectory(event)
        cfg = config or {}
        min_confidence = cfg.get("min_confidence", 65.0)
        atr_sl_mult = cfg.get("atr_sl_mult", 1.5)
        atr_tp1_mult = cfg.get("atr_tp1_mult", 2.0)
        atr_tp2_mult = cfg.get("atr_tp2_mult", 3.5)

        trades: List[Dict] = []
        position: Optional[Dict] = None
        equity = 50000.0
        initial_equity = equity
        peak_equity = equity
        equity_curve = []

        # EMA state for signal calculation
        ema_fast = bars[0]["price"]
        ema_slow = bars[0]["price"]
        ema_fast_alpha = 0.15  # ~13-bar EMA
        ema_slow_alpha = 0.05  # ~40-bar EMA
        prev_price = bars[0]["price"]

        for i, bar in enumerate(bars):
            price = bar["price"]
            regime = bar["regime"]
            adx = bar["adx"]
            atr = bar["atr"]
            spread = bar["spread"]
            vol_ratio = bar["vol_ratio"]
            fragility = bar["fragility_score"]

            # Update EMAs
            ema_fast = ema_fast_alpha * price + (1 - ema_fast_alpha) * ema_fast
            ema_slow = ema_slow_alpha * price + (1 - ema_slow_alpha) * ema_slow
            price_change_pct = ((price - prev_price) / prev_price * 100) if prev_price > 0 else 0
            prev_price = price

            # --- Manage existing position ---
            if position is not None:
                direction = position["direction"]
                entry = position["entry_price"]
                size = position["size"]
                remaining = position["remaining_size"]

                if direction == "long":
                    unrealized_per_unit = price - entry
                else:
                    unrealized_per_unit = entry - price

                # Check TP1 (partial close 50%)
                if not position["tp1_hit"]:
                    tp1_price = position["take_profit_1"]
                    hit_tp1 = (price >= tp1_price) if direction == "long" else (price <= tp1_price)
                    if hit_tp1:
                        close_size = remaining // 2 if remaining > 1 else remaining
                        pnl = unrealized_per_unit * close_size * 1000
                        equity += pnl
                        position["tp1_hit"] = True
                        position["remaining_size"] = remaining - close_size
                        position["sl_moved_to_be"] = True
                        position["stop_loss"] = entry  # Move SL to breakeven
                        position["partial_closes"].append({
                            "bar": bar["bar"],
                            "price": price,
                            "size_closed": close_size,
                            "pnl": round(pnl, 2),
                            "reason": "TP1"
                        })
                        remaining = position["remaining_size"]

                # Check TP2 (close rest)
                if position["tp1_hit"] and remaining > 0:
                    tp2_price = position["take_profit_2"]
                    hit_tp2 = (price >= tp2_price) if direction == "long" else (price <= tp2_price)
                    if hit_tp2:
                        pnl = unrealized_per_unit * remaining * 1000
                        equity += pnl
                        position["partial_closes"].append({
                            "bar": bar["bar"],
                            "price": price,
                            "size_closed": remaining,
                            "pnl": round(pnl, 2),
                            "reason": "TP2"
                        })
                        position["exit_bar"] = bar["bar"]
                        position["exit_price"] = price
                        position["exit_reason"] = "TP2_FULL"
                        total_pnl = sum(pc["pnl"] for pc in position["partial_closes"])
                        position["total_pnl"] = round(total_pnl, 2)
                        trades.append(position)
                        position = None

                # Check SL
                if position is not None:
                    sl_price = position["stop_loss"]
                    hit_sl = (price <= sl_price) if direction == "long" else (price >= sl_price)
                    if hit_sl:
                        pnl = unrealized_per_unit * remaining * 1000
                        equity += pnl
                        position["partial_closes"].append({
                            "bar": bar["bar"],
                            "price": price,
                            "size_closed": remaining,
                            "pnl": round(pnl, 2),
                            "reason": "SL" if not position.get("sl_moved_to_be") else "BE_SL"
                        })
                        position["exit_bar"] = bar["bar"]
                        position["exit_price"] = price
                        position["exit_reason"] = "STOP_LOSS" if not position.get("sl_moved_to_be") else "BREAKEVEN_SL"
                        total_pnl = sum(pc["pnl"] for pc in position["partial_closes"])
                        position["total_pnl"] = round(total_pnl, 2)
                        trades.append(position)
                        position = None

            # --- Generate new signal if no position ---
            if position is None and i >= 5:  # Need min bars for EMAs
                # Compute signal score (simplified from SignalScorer)
                ema_pct = (ema_fast - ema_slow) / ema_slow * 100 if ema_slow > 0 else 0
                ema_score = max(-20, min(20, ema_pct * 10))

                if adx > 28:
                    adx_score = 15 if price_change_pct > 0 else -15
                elif adx > 22:
                    adx_score = 8 if price_change_pct > 0 else -8
                else:
                    adx_score = 0

                regime_map = {"normal": 5, "event": 0, "spike": -5, "blocked": -15}
                regime_score = regime_map.get(regime, 0)
                if regime == "normal":
                    regime_score = 10 if price_change_pct > 0 else -5

                vol_score = 5 if vol_ratio < 0.8 else (0 if vol_ratio < 1.5 else (-5 if vol_ratio < 2.5 else -10))
                mom_score = max(-15, min(15, price_change_pct * 5))
                spread_score = 5 if spread < 0.03 else (0 if spread < 0.08 else -5)
                frag_score_val = 10 if fragility < 20 else (5 if fragility < 40 else (0 if fragility < 60 else (-5 if fragility < 80 else -10)))

                total_signal = ema_score + adx_score + regime_score + vol_score + mom_score + spread_score + frag_score_val
                total_signal = max(-100, min(100, total_signal))
                abs_signal = abs(total_signal)

                # Compute composite confidence (from bot logic)
                signal_confidence = min(100, abs_signal * 1.2)
                gate_bonus = 15 if fragility < 30 and regime == "normal" else (5 if fragility < 60 else -10)
                frag_penalty = fragility * 0.3
                regime_bonus = {"normal": 10, "event": -5, "spike": -20, "blocked": -40}.get(regime, -10)
                composite = max(0, min(100, signal_confidence + gate_bonus - frag_penalty + regime_bonus))

                if composite >= min_confidence and abs(total_signal) >= 15:
                    direction = "long" if total_signal > 0 else "short"
                    safe_atr = max(0.1, atr)

                    if direction == "long":
                        sl = round(price - safe_atr * atr_sl_mult, 2)
                        tp1 = round(price + safe_atr * atr_tp1_mult, 2)
                        tp2 = round(price + safe_atr * atr_tp2_mult, 2)
                    else:
                        sl = round(price + safe_atr * atr_sl_mult, 2)
                        tp1 = round(price - safe_atr * atr_tp1_mult, 2)
                        tp2 = round(price - safe_atr * atr_tp2_mult, 2)

                    risk_per_contract = abs(price - sl) * 1000
                    max_risk = equity * 0.01
                    trade_size = max(1, int(max_risk / max(1, risk_per_contract)))

                    position = {
                        "id": f"sim_{len(trades)+1}",
                        "direction": direction,
                        "entry_bar": bar["bar"],
                        "entry_price": price,
                        "stop_loss": sl,
                        "take_profit_1": tp1,
                        "take_profit_2": tp2,
                        "size": trade_size,
                        "remaining_size": trade_size,
                        "confidence": round(composite, 1),
                        "signal_score": round(total_signal, 1),
                        "regime_at_entry": regime,
                        "fragility_at_entry": round(fragility, 1),
                        "tp1_hit": False,
                        "sl_moved_to_be": False,
                        "partial_closes": [],
                        "exit_bar": None,
                        "exit_price": None,
                        "exit_reason": None,
                        "total_pnl": 0.0,
                    }

            # Track equity curve
            if peak_equity < equity:
                peak_equity = equity
            equity_curve.append({
                "bar": bar["bar"],
                "equity": round(equity, 2),
                "drawdown_pct": round((peak_equity - equity) / peak_equity * 100, 2) if peak_equity > 0 else 0,
            })

        # Close any remaining position at last bar price
        if position is not None:
            last_price = bars[-1]["price"]
            direction = position["direction"]
            remaining = position["remaining_size"]
            if direction == "long":
                unrealized = (last_price - position["entry_price"]) * remaining * 1000
            else:
                unrealized = (position["entry_price"] - last_price) * remaining * 1000
            equity += unrealized
            position["partial_closes"].append({
                "bar": bars[-1]["bar"],
                "price": last_price,
                "size_closed": remaining,
                "pnl": round(unrealized, 2),
                "reason": "EVENT_END"
            })
            position["exit_bar"] = bars[-1]["bar"]
            position["exit_price"] = last_price
            position["exit_reason"] = "EVENT_END"
            position["total_pnl"] = round(sum(pc["pnl"] for pc in position["partial_closes"]), 2)
            trades.append(position)

        # Summary
        total_pnl = sum(t["total_pnl"] for t in trades)
        win_trades = [t for t in trades if t["total_pnl"] > 0]
        loss_trades = [t for t in trades if t["total_pnl"] <= 0]
        max_win = max((t["total_pnl"] for t in trades), default=0)
        max_loss = min((t["total_pnl"] for t in trades), default=0)
        max_dd = max((ec["drawdown_pct"] for ec in equity_curve), default=0)

        return {
            "event": {
                "id": event_id,
                "name": event["name"],
                "description": event["description"],
                "date": event["date"],
            },
            "config": {
                "min_confidence": min_confidence,
                "atr_sl_mult": atr_sl_mult,
                "atr_tp1_mult": atr_tp1_mult,
                "atr_tp2_mult": atr_tp2_mult,
            },
            "trades": trades,
            "equity_curve": equity_curve,
            "summary": {
                "total_trades": len(trades),
                "winning_trades": len(win_trades),
                "losing_trades": len(loss_trades),
                "win_rate": round(len(win_trades) / len(trades) * 100, 1) if trades else 0,
                "total_pnl": round(total_pnl, 2),
                "max_win": round(max_win, 2),
                "max_loss": round(max_loss, 2),
                "final_equity": round(equity, 2),
                "return_pct": round((equity - initial_equity) / initial_equity * 100, 2),
                "max_drawdown_pct": round(max_dd, 2),
                "profit_factor": round(sum(t["total_pnl"] for t in win_trades) / abs(sum(t["total_pnl"] for t in loss_trades)), 2) if loss_trades and sum(t["total_pnl"] for t in loss_trades) != 0 else 999.0,
            },
        }


# Global instance
replay_engine = ReplayEngine()
