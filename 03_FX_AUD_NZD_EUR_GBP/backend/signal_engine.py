"""
Signal generation engine.
Evaluates market conditions and produces trading signals with confidence scores.
"""
from __future__ import annotations

import numpy as np
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional
from database import get_setting, get_recent_prices, insert_signal, insert_log
from indicators import TechnicalIndicators
from market_data import MarketDataService


@dataclass
class Signal:
    pair: str
    direction: str  # BUY, SELL, WAIT
    confidence: float  # 0-100
    regime: str  # TREND, RANGE, EVENT
    reason: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


class SignalEngine:
    """Generates trading signals based on technical indicators and system state."""

    def __init__(self, market_data: MarketDataService):
        self._market_data = market_data
        self._indicators = TechnicalIndicators()
        self._latest_signals: dict[str, Signal] = {}

    def get_latest_signal(self, pair: str) -> Optional[Signal]:
        return self._latest_signals.get(pair)

    def get_all_latest_signals(self) -> dict[str, dict]:
        return {pair: sig.to_dict() for pair, sig in self._latest_signals.items()}

    async def generate_signal(
        self,
        pair: str,
        indicators: dict,
        direction_permission: str,
        event_state: dict,
        override_mode: str,
    ) -> Signal:
        """
        Generate a trading signal for the given pair.

        Args:
            pair: Currency pair (e.g. "AUD/USD")
            indicators: Dict from MarketDataService.compute_indicators() with underscore-prefixed arrays
            direction_permission: LONG_ONLY, SHORT_ONLY, or BOTH
            event_state: Dict with 'state' and 'remaining_seconds' from EventEngine
            override_mode: NORMAL, OBSERVE_ONLY, REDUCE_ONLY, FLATTEN_ALL
        """
        now = datetime.now(timezone.utc).isoformat()

        # ── Override checks ───────────────────────────────────────────────
        kill_switch = await get_setting("kill_switch")
        if kill_switch and kill_switch.lower() == "true":
            return self._make_signal(pair, "WAIT", 0, "RANGE", "Kill switch is active", now)

        if override_mode == "OBSERVE_ONLY":
            return self._make_signal(pair, "WAIT", 0, "RANGE", "System in OBSERVE_ONLY mode", now)

        if override_mode == "FLATTEN_ALL":
            return self._make_signal(pair, "WAIT", 0, "RANGE", "System in FLATTEN_ALL mode", now)

        # ── Event cooldown check ──────────────────────────────────────────
        if event_state.get("state") in ("PRE_EVENT", "COOLDOWN"):
            remaining = event_state.get("remaining_seconds", 0)
            return self._make_signal(
                pair, "WAIT", 0, "EVENT",
                f"Event cooldown active ({remaining:.0f}s remaining)", now,
            )

        # ── Extract indicator arrays ──────────────────────────────────────
        closes = indicators.get("_closes")
        sma20_arr = indicators.get("_sma20")
        sma50_arr = indicators.get("_sma50")
        adx_arr = indicators.get("_adx")
        rsi_arr = indicators.get("_rsi")
        bb_upper = indicators.get("_bb_upper")
        bb_lower = indicators.get("_bb_lower")
        atr_arr = indicators.get("_atr")

        if closes is None or len(closes) < 20:
            return self._make_signal(pair, "WAIT", 0, "RANGE", "Insufficient price data", now)

        # Get latest valid values
        price = closes[-1]
        sma20 = self._latest_valid(sma20_arr)
        sma50 = self._latest_valid(sma50_arr)
        adx = self._latest_valid(adx_arr)
        rsi = self._latest_valid(rsi_arr)
        upper_bb = self._latest_valid(bb_upper)
        lower_bb = self._latest_valid(bb_lower)
        atr = self._latest_valid(atr_arr)

        if sma20 is None or rsi is None:
            return self._make_signal(pair, "WAIT", 0, "RANGE", "Indicators not ready", now)

        # Default ADX to 15 if not computed yet
        if adx is None:
            adx = 15.0

        # ── Determine regime ──────────────────────────────────────────────
        regime = "TREND" if adx > 25 else "RANGE"

        # ── Spread penalty ────────────────────────────────────────────────
        spread_threshold_str = await get_setting("spread_threshold_pips")
        spread_threshold = float(spread_threshold_str) if spread_threshold_str else 3.0
        # We don't have live spread in indicators, assume acceptable for now
        spread_penalty = 1.0

        # ── TREND regime signals ──────────────────────────────────────────
        if regime == "TREND":
            if sma50 is not None:
                # BUY signal: price > SMA20 > SMA50, RSI < 70
                if (
                    direction_permission in ("LONG_ONLY", "BOTH")
                    and price > sma20 > sma50
                    and rsi < 70
                ):
                    base_confidence = 60.0
                    adx_factor = min(adx / 50.0, 1.5)
                    rsi_bonus = (70 - rsi) / 70 * 10  # Stronger signal when RSI not overbought
                    confidence = min(base_confidence * adx_factor * spread_penalty + rsi_bonus, 100)
                    reason = (
                        f"TREND BUY: price({price:.5f}) > SMA20({sma20:.5f}) > SMA50({sma50:.5f}), "
                        f"RSI={rsi:.1f}, ADX={adx:.1f}"
                    )
                    signal = self._make_signal(pair, "BUY", confidence, regime, reason, now)
                    await self._store_signal(signal)
                    return signal

                # SELL signal: price < SMA20 < SMA50, RSI > 30
                if (
                    direction_permission in ("SHORT_ONLY", "BOTH")
                    and price < sma20 < sma50
                    and rsi > 30
                ):
                    base_confidence = 60.0
                    adx_factor = min(adx / 50.0, 1.5)
                    rsi_bonus = (rsi - 30) / 70 * 10
                    confidence = min(base_confidence * adx_factor * spread_penalty + rsi_bonus, 100)
                    reason = (
                        f"TREND SELL: price({price:.5f}) < SMA20({sma20:.5f}) < SMA50({sma50:.5f}), "
                        f"RSI={rsi:.1f}, ADX={adx:.1f}"
                    )
                    signal = self._make_signal(pair, "SELL", confidence, regime, reason, now)
                    await self._store_signal(signal)
                    return signal
            else:
                # Only SMA20 available
                if direction_permission in ("LONG_ONLY", "BOTH") and price > sma20 and rsi < 70:
                    confidence = min(40.0 * min(adx / 50.0, 1.5), 100)
                    reason = f"TREND BUY (SMA20 only): price({price:.5f}) > SMA20({sma20:.5f}), RSI={rsi:.1f}"
                    signal = self._make_signal(pair, "BUY", confidence, regime, reason, now)
                    await self._store_signal(signal)
                    return signal

        # ── RANGE regime signals ──────────────────────────────────────────
        if regime == "RANGE" and upper_bb is not None and lower_bb is not None:
            bb_width = upper_bb - lower_bb
            if bb_width > 0:
                # BUY near lower Bollinger when RSI oversold
                if (
                    direction_permission in ("LONG_ONLY", "BOTH")
                    and price <= lower_bb + bb_width * 0.1
                    and rsi < 35
                ):
                    base_confidence = 40.0
                    rsi_factor = (35 - rsi) / 35
                    proximity = 1.0 - ((price - lower_bb) / bb_width) if bb_width > 0 else 0.5
                    confidence = min(base_confidence + rsi_factor * 20 + proximity * 15, 85)
                    reason = (
                        f"RANGE BUY: price({price:.5f}) near lower BB({lower_bb:.5f}), "
                        f"RSI={rsi:.1f}"
                    )
                    signal = self._make_signal(pair, "BUY", confidence, regime, reason, now)
                    await self._store_signal(signal)
                    return signal

                # SELL near upper Bollinger when RSI overbought
                if (
                    direction_permission in ("SHORT_ONLY", "BOTH")
                    and price >= upper_bb - bb_width * 0.1
                    and rsi > 65
                ):
                    base_confidence = 40.0
                    rsi_factor = (rsi - 65) / 35
                    proximity = ((price - lower_bb) / bb_width) if bb_width > 0 else 0.5
                    confidence = min(base_confidence + rsi_factor * 20 + proximity * 15, 85)
                    reason = (
                        f"RANGE SELL: price({price:.5f}) near upper BB({upper_bb:.5f}), "
                        f"RSI={rsi:.1f}"
                    )
                    signal = self._make_signal(pair, "SELL", confidence, regime, reason, now)
                    await self._store_signal(signal)
                    return signal

        # ── REDUCE_ONLY override ──────────────────────────────────────────
        if override_mode == "REDUCE_ONLY":
            return self._make_signal(pair, "WAIT", 0, regime, "REDUCE_ONLY mode - no new positions", now)

        # ── No signal conditions met ──────────────────────────────────────
        return self._make_signal(pair, "WAIT", 0, regime, "No signal conditions met", now)

    def _make_signal(
        self, pair: str, direction: str, confidence: float,
        regime: str, reason: str, timestamp: str,
    ) -> Signal:
        sig = Signal(
            pair=pair,
            direction=direction,
            confidence=round(confidence, 1),
            regime=regime,
            reason=reason,
            timestamp=timestamp,
        )
        self._latest_signals[pair] = sig
        return sig

    async def _store_signal(self, signal: Signal) -> None:
        await insert_signal(
            pair=signal.pair,
            timestamp=signal.timestamp,
            direction=signal.direction,
            confidence=signal.confidence,
            regime=signal.regime,
            reason=signal.reason,
        )

    @staticmethod
    def _latest_valid(arr: Optional[np.ndarray]) -> Optional[float]:
        if arr is None:
            return None
        for v in reversed(arr):
            if not np.isnan(v):
                return float(v)
        return None

    async def evaluate_all(self, event_state: dict) -> list[Signal]:
        """Evaluate signals for all pairs. Called by the main loop."""
        signals = []
        override_mode = await get_setting("override_mode") or "NORMAL"

        for pair in ["AUD/USD", "NZD/USD"]:
            # Get direction permission
            key = pair.replace("/", "_").lower() + "_direction"
            direction_permission = await get_setting(key) or "LONG_ONLY"

            # Fetch latest indicators
            result = await self._market_data.poll_once(pair)
            if result is None:
                continue

            indicators = result.get("indicators", {})
            signal = await self.generate_signal(
                pair=pair,
                indicators=indicators,
                direction_permission=direction_permission,
                event_state=event_state,
                override_mode=override_mode,
            )
            signals.append(signal)

            # Broadcast signal
            if signal.direction != "WAIT":
                await self._market_data.broadcast({
                    "type": "signal",
                    "data": signal.to_dict(),
                })

        return signals
