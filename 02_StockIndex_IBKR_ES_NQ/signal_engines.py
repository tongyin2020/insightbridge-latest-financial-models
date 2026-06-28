"""
Signal Engines — Four Model Signal Logic
Uses real-time IBKR market data to generate trading signals

Models:
  CryptoSignalEngine  → BTC / ETH / SOL  (EMA crossover + RSI)
  FXSignalEngine      → AUD/USD NZD/USD  (EMA + ADX trend filter)
  BondSignalEngine    → ZN Treasury      (Mean reversion + trend)
  OilSignalEngine     → CL WTI Crude     (EMA + ATR + ADX)
  IndexSignalEngine   → MES S&P micro    (EMA + RSI breakout filter)
"""

from dataclasses import dataclass
from typing import Optional, List


# ─── Signal Dataclass ─────────────────────────────────────────────────────────

@dataclass
class Signal:
    model:      str
    symbol:     str
    direction:  str            # "BUY" or "SELL"
    order_type: str            # "market" or "limit"
    quantity:   float
    price:      Optional[float]  # limit price (None for market orders)
    confidence: float
    reason:     str


# ─── Technical Indicator Helpers ──────────────────────────────────────────────

def calc_ema(prices: List[float], period: int) -> List[float]:
    k = 2 / (period + 1)
    result = []
    for i, p in enumerate(prices):
        result.append(p if i == 0 else p * k + result[-1] * (1 - k))
    return result


def calc_rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains  = [d if d > 0 else 0.0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0.0 for d in deltas[-period:]]
    avg_g  = sum(gains) / period
    avg_l  = sum(losses) / period
    if avg_l == 0:
        return 100.0
    return 100 - (100 / (1 + avg_g / avg_l))


def calc_atr(highs: List[float], lows: List[float], closes: List[float],
             period: int = 14) -> float:
    if len(closes) < 2:
        return 0.0
    trs = [max(highs[i] - lows[i],
               abs(highs[i] - closes[i - 1]),
               abs(lows[i]  - closes[i - 1]))
           for i in range(1, len(closes))]
    return sum(trs[-period:]) / min(len(trs), period)


def calc_adx(highs: List[float], lows: List[float], closes: List[float],
             period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    dm_plus, dm_minus = [], []
    for i in range(1, len(closes)):
        up   = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        dm_plus.append(up   if up > down and up > 0 else 0.0)
        dm_minus.append(down if down > up and down > 0 else 0.0)
    atr_val = calc_atr(highs, lows, closes, period)
    if atr_val == 0:
        return 0.0
    di_p = 100 * sum(dm_plus[-period:])  / (atr_val * period)
    di_m = 100 * sum(dm_minus[-period:]) / (atr_val * period)
    if di_p + di_m == 0:
        return 0.0
    return 100 * abs(di_p - di_m) / (di_p + di_m)


# ─── Crypto Signal Engine ─────────────────────────────────────────────────────

class CryptoSignalEngine:
    """
    BTC / ETH / SOL
    Strategy: EMA(9/21) crossover + RSI confirmation
    Order type: Market (cashQty in USD)
    """

    def __init__(self, symbol: str, quantity: float = 100):
        self.symbol      = symbol
        self.quantity    = quantity   # USD cash amount
        self.prices:     List[float] = []
        self.last_signal: Optional[str] = None

    def update(self, price: float) -> Optional[Signal]:
        self.prices.append(price)
        if len(self.prices) < 30:
            return None

        px       = self.prices[-60:]
        ema_fast = calc_ema(px, 9)
        ema_slow = calc_ema(px, 21)
        rsi_val  = calc_rsi(px, 14)

        cross_up   = ema_fast[-2] <= ema_slow[-2] and ema_fast[-1] > ema_slow[-1]
        cross_down = ema_fast[-2] >= ema_slow[-2] and ema_fast[-1] < ema_slow[-1]
        trend_up   = ema_fast[-1] > ema_slow[-1]
        trend_down = ema_fast[-1] < ema_slow[-1]

        direction, confidence, reasons = None, 0.0, []

        if cross_up and rsi_val < 70:
            direction, confidence = "BUY", 0.70 + (0.05 if rsi_val < 50 else 0)
            reasons = [f"EMA9/21 crossover UP", f"RSI={rsi_val:.1f}"]
        elif cross_down and rsi_val > 30:
            direction, confidence = "SELL", 0.70 + (0.05 if rsi_val > 50 else 0)
            reasons = [f"EMA9/21 crossover DOWN", f"RSI={rsi_val:.1f}"]
        elif trend_up and rsi_val < 40:
            direction, confidence = "BUY", 0.63
            reasons = [f"Uptrend + RSI oversold={rsi_val:.1f}"]
        elif trend_down and rsi_val > 60:
            direction, confidence = "SELL", 0.63
            reasons = [f"Downtrend + RSI overbought={rsi_val:.1f}"]

        if direction and confidence >= 0.60:
            if direction == self.last_signal:
                return None  # avoid duplicate signals
            self.last_signal = direction
            return Signal(
                model="crypto", symbol=self.symbol,
                direction=direction, order_type="market",
                quantity=self.quantity, price=None,
                confidence=confidence, reason=" + ".join(reasons)
            )
        return None


# ─── FX Signal Engine ─────────────────────────────────────────────────────────

class FXSignalEngine:
    """
    AUD/USD / NZD/USD
    Strategy: EMA(9/21) crossover + ADX trend strength filter
    Order type: Limit (slightly inside spread)
    """

    def __init__(self, symbol: str, quantity: float = 25000):
        self.symbol      = symbol
        self.quantity    = quantity   # FX units (min 25,000 for IDEALPRO)
        self.closes:     List[float] = []
        self.highs:      List[float] = []
        self.lows:       List[float] = []
        self.last_signal: Optional[str] = None

    def update(self, price: float,
               high: float = None, low: float = None) -> Optional[Signal]:
        self.closes.append(price)
        self.highs.append(high  or price * 1.0005)
        self.lows.append( low   or price * 0.9995)

        if len(self.closes) < 30:
            return None

        cl = self.closes[-80:]
        hi = self.highs[-80:]
        lo = self.lows[-80:]

        ema9    = calc_ema(cl, 9)
        ema21   = calc_ema(cl, 21)
        adx_val = calc_adx(hi, lo, cl, 14)
        rsi_val = calc_rsi(cl, 14)

        cross_up   = ema9[-2] <= ema21[-2] and ema9[-1] > ema21[-1]
        cross_down = ema9[-2] >= ema21[-2] and ema9[-1] < ema21[-1]

        direction, confidence, reasons = None, 0.0, []

        if cross_up and adx_val > 20 and rsi_val < 65:
            direction, confidence = "BUY", 0.65 + min(0.15, (adx_val - 20) / 100)
            reasons = [f"EMA crossover UP", f"ADX={adx_val:.1f}", f"RSI={rsi_val:.1f}"]
        elif cross_down and adx_val > 20 and rsi_val > 35:
            direction, confidence = "SELL", 0.65 + min(0.15, (adx_val - 20) / 100)
            reasons = [f"EMA crossover DOWN", f"ADX={adx_val:.1f}", f"RSI={rsi_val:.1f}"]

        if direction and confidence >= 0.60:
            if direction == self.last_signal:
                return None
            self.last_signal = direction
            # Limit price: 2 pips inside market
            offset = 0.0002
            lp = round(price - offset if direction == "BUY" else price + offset, 5)
            return Signal(
                model="fx", symbol=self.symbol,
                direction=direction, order_type="limit",
                quantity=self.quantity, price=lp,
                confidence=confidence, reason=" + ".join(reasons)
            )
        return None


# ─── Bond Signal Engine ───────────────────────────────────────────────────────

class BondSignalEngine:
    """
    ZN 10Y Treasury Note Futures
    Strategy: EMA(20/50) crossover + mean reversion from EMA20
    Order type: Market
    """

    def __init__(self, quantity: int = 1):
        self.quantity    = quantity
        self.closes:     List[float] = []
        self.highs:      List[float] = []
        self.lows:       List[float] = []
        self.last_signal: Optional[str] = None

    def update(self, price: float,
               high: float = None, low: float = None) -> Optional[Signal]:
        self.closes.append(price)
        self.highs.append(high or price + 0.0625)
        self.lows.append( low  or price - 0.0625)

        if len(self.closes) < 35:
            return None

        cl  = self.closes[-80:]
        hi  = self.highs[-80:]
        lo  = self.lows[-80:]

        ema20   = calc_ema(cl, 20)
        ema50   = calc_ema(cl, min(50, len(cl)))
        atr_val = calc_atr(hi, lo, cl, 14)
        rsi_val = calc_rsi(cl, 14)

        trend_up   = ema20[-1] > ema50[-1]
        trend_down = ema20[-1] < ema50[-1]
        dev        = cl[-1] - ema20[-1]

        cross_up   = ema20[-2] <= ema50[-2] and ema20[-1] > ema50[-1]
        cross_down = ema20[-2] >= ema50[-2] and ema20[-1] < ema50[-1]

        direction, confidence, reasons = None, 0.0, []

        if cross_up:
            direction, confidence = "BUY", 0.73
            reasons = ["EMA20 crosses above EMA50 — trend reversal UP"]
        elif cross_down:
            direction, confidence = "SELL", 0.73
            reasons = ["EMA20 crosses below EMA50 — trend reversal DOWN"]
        elif trend_up and dev < -atr_val * 0.5 and rsi_val < 45:
            direction, confidence = "BUY", 0.68
            reasons = [f"Mean reversion BUY", f"dev={dev:.3f}", f"RSI={rsi_val:.1f}"]
        elif trend_down and dev > atr_val * 0.5 and rsi_val > 55:
            direction, confidence = "SELL", 0.68
            reasons = [f"Mean reversion SELL", f"dev=+{dev:.3f}", f"RSI={rsi_val:.1f}"]

        if direction and confidence >= 0.60:
            if direction == self.last_signal:
                return None
            self.last_signal = direction
            return Signal(
                model="bond", symbol="ZN",
                direction=direction, order_type="market",
                quantity=self.quantity, price=None,
                confidence=confidence, reason=" + ".join(reasons)
            )
        return None


# ─── Oil Signal Engine ────────────────────────────────────────────────────────

class OilSignalEngine:
    """
    CL WTI Crude Oil Futures
    Strategy: EMA(9/21) crossover + ADX trend strength + ATR-based limit price
    Order type: Limit
    """

    def __init__(self, quantity: int = 1):
        self.quantity    = quantity
        self.closes:     List[float] = []
        self.highs:      List[float] = []
        self.lows:       List[float] = []
        self.last_signal: Optional[str] = None

    def update(self, price: float,
               high: float = None, low: float = None) -> Optional[Signal]:
        self.closes.append(price)
        self.highs.append(high or price + 0.25)
        self.lows.append( low  or price - 0.25)

        if len(self.closes) < 30:
            return None

        cl  = self.closes[-80:]
        hi  = self.highs[-80:]
        lo  = self.lows[-80:]

        ema9    = calc_ema(cl, 9)
        ema21   = calc_ema(cl, 21)
        atr_val = calc_atr(hi, lo, cl, 14)
        adx_val = calc_adx(hi, lo, cl, 14)
        rsi_val = calc_rsi(cl, 14)

        cross_up   = ema9[-2] <= ema21[-2] and ema9[-1] > ema21[-1]
        cross_down = ema9[-2] >= ema21[-2] and ema9[-1] < ema21[-1]

        direction, confidence, reasons = None, 0.0, []

        if cross_up and adx_val > 20 and rsi_val < 65:
            direction, confidence = "BUY", 0.70 + min(0.10, (adx_val - 20) / 100)
            reasons = [f"EMA9/21 crossover UP", f"ADX={adx_val:.1f}", f"ATR={atr_val:.2f}"]
        elif cross_down and adx_val > 20 and rsi_val > 35:
            direction, confidence = "SELL", 0.70 + min(0.10, (adx_val - 20) / 100)
            reasons = [f"EMA9/21 crossover DOWN", f"ADX={adx_val:.1f}", f"ATR={atr_val:.2f}"]

        if direction and confidence >= 0.60:
            if direction == self.last_signal:
                return None
            self.last_signal = direction
            # Limit price: entry 0.3×ATR inside market
            offset = round(atr_val * 0.3, 2)
            lp = round(cl[-1] - offset if direction == "BUY" else cl[-1] + offset, 2)
            return Signal(
                model="oil", symbol="CL",
                direction=direction, order_type="limit",
                quantity=self.quantity, price=lp,
                confidence=confidence, reason=" + ".join(reasons)
            )
        return None


class IndexSignalEngine:
    """
    MES Micro E-mini S&P 500
    Strategy: EMA(9/21) crossover + RSI breakout confirmation
    Order type: Market
    """

    def __init__(self, quantity: int = 1):
        self.quantity = quantity
        self.closes: List[float] = []
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.last_signal: Optional[str] = None

    def update(self, price: float,
               high: float = None, low: float = None) -> Optional[Signal]:
        self.closes.append(price)
        self.highs.append(high or price + 8.0)
        self.lows.append(low or price - 8.0)

        if len(self.closes) < 30:
            return None

        cl = self.closes[-80:]
        ema9 = calc_ema(cl, 9)
        ema21 = calc_ema(cl, 21)
        rsi_val = calc_rsi(cl, 14)

        cross_up = ema9[-2] <= ema21[-2] and ema9[-1] > ema21[-1]
        cross_down = ema9[-2] >= ema21[-2] and ema9[-1] < ema21[-1]

        direction, confidence, reasons = None, 0.0, []
        if cross_up and rsi_val < 68:
            direction, confidence = "BUY", 0.69 + (0.05 if rsi_val < 55 else 0.0)
            reasons = [f"EMA9/21 crossover UP", f"RSI={rsi_val:.1f}"]
        elif cross_down and rsi_val > 32:
            direction, confidence = "SELL", 0.69 + (0.05 if rsi_val > 45 else 0.0)
            reasons = [f"EMA9/21 crossover DOWN", f"RSI={rsi_val:.1f}"]

        if direction and confidence >= 0.60:
            if direction == self.last_signal:
                return None
            self.last_signal = direction
            return Signal(
                model="index", symbol="MES",
                direction=direction, order_type="market",
                quantity=self.quantity, price=None,
                confidence=confidence, reason=" + ".join(reasons)
            )
        return None
