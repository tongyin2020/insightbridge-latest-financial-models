"""
Technical indicators calculated manually using numpy/pandas.
All functions work on numpy arrays and return numpy arrays.
"""
from __future__ import annotations

import numpy as np
from typing import Optional


class TechnicalIndicators:

    @staticmethod
    def calculate_sma(prices: np.ndarray, period: int) -> np.ndarray:
        """Simple Moving Average."""
        sma = np.full_like(prices, np.nan, dtype=np.float64)
        if len(prices) < period:
            return sma
        cumsum = np.cumsum(prices, dtype=np.float64)
        cumsum[period:] = cumsum[period:] - cumsum[:-period]
        sma[period - 1:] = cumsum[period - 1:] / period
        return sma

    @staticmethod
    def calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average."""
        ema = np.full_like(prices, np.nan, dtype=np.float64)
        if len(prices) < period:
            return ema
        multiplier = 2.0 / (period + 1)
        # Seed with SMA of first `period` values
        ema[period - 1] = np.mean(prices[:period])
        for i in range(period, len(prices)):
            ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
        return ema

    @staticmethod
    def calculate_adx(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int = 14,
    ) -> np.ndarray:
        """Average Directional Index (ADX)."""
        n = len(closes)
        adx = np.full(n, np.nan, dtype=np.float64)
        if n < period * 2:
            return adx

        # True Range
        tr = np.zeros(n, dtype=np.float64)
        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr[i] = max(hl, hc, lc)

        # +DM and -DM
        plus_dm = np.zeros(n, dtype=np.float64)
        minus_dm = np.zeros(n, dtype=np.float64)
        for i in range(1, n):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move

        # Smoothed TR, +DM, -DM using Wilder's smoothing
        atr_smooth = np.zeros(n, dtype=np.float64)
        plus_dm_smooth = np.zeros(n, dtype=np.float64)
        minus_dm_smooth = np.zeros(n, dtype=np.float64)

        atr_smooth[period] = np.sum(tr[1:period + 1])
        plus_dm_smooth[period] = np.sum(plus_dm[1:period + 1])
        minus_dm_smooth[period] = np.sum(minus_dm[1:period + 1])

        for i in range(period + 1, n):
            atr_smooth[i] = atr_smooth[i - 1] - (atr_smooth[i - 1] / period) + tr[i]
            plus_dm_smooth[i] = plus_dm_smooth[i - 1] - (plus_dm_smooth[i - 1] / period) + plus_dm[i]
            minus_dm_smooth[i] = minus_dm_smooth[i - 1] - (minus_dm_smooth[i - 1] / period) + minus_dm[i]

        # +DI and -DI
        plus_di = np.zeros(n, dtype=np.float64)
        minus_di = np.zeros(n, dtype=np.float64)
        dx = np.zeros(n, dtype=np.float64)

        for i in range(period, n):
            if atr_smooth[i] != 0:
                plus_di[i] = 100.0 * plus_dm_smooth[i] / atr_smooth[i]
                minus_di[i] = 100.0 * minus_dm_smooth[i] / atr_smooth[i]
            di_sum = plus_di[i] + minus_di[i]
            if di_sum != 0:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

        # ADX = smoothed DX
        start = period * 2
        if start < n:
            adx[start] = np.mean(dx[period:start + 1])
            for i in range(start + 1, n):
                adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return adx

    @staticmethod
    def calculate_atr(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        period: int = 14,
    ) -> np.ndarray:
        """Average True Range."""
        n = len(closes)
        atr = np.full(n, np.nan, dtype=np.float64)
        if n < period + 1:
            return atr

        tr = np.zeros(n, dtype=np.float64)
        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr[i] = max(hl, hc, lc)

        # Wilder's smoothing
        atr[period] = np.mean(tr[1:period + 1])
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        return atr

    @staticmethod
    def calculate_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
        """Relative Strength Index."""
        n = len(closes)
        rsi = np.full(n, np.nan, dtype=np.float64)
        if n < period + 1:
            return rsi

        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        if avg_loss == 0:
            rsi[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100.0 - (100.0 / (1.0 + rs))

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i + 1] = 100.0 - (100.0 / (1.0 + rs))

        return rsi

    @staticmethod
    def calculate_bollinger(
        closes: np.ndarray,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Bollinger Bands. Returns (upper, middle, lower)."""
        n = len(closes)
        middle = np.full(n, np.nan, dtype=np.float64)
        upper = np.full(n, np.nan, dtype=np.float64)
        lower = np.full(n, np.nan, dtype=np.float64)

        if n < period:
            return upper, middle, lower

        for i in range(period - 1, n):
            window = closes[i - period + 1: i + 1]
            mean = np.mean(window)
            std = np.std(window, ddof=0)
            middle[i] = mean
            upper[i] = mean + std_dev * std
            lower[i] = mean - std_dev * std

        return upper, middle, lower

    @staticmethod
    def calculate_vwap(
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
    ) -> np.ndarray:
        """Volume Weighted Average Price (cumulative)."""
        n = len(closes)
        vwap = np.full(n, np.nan, dtype=np.float64)
        if n == 0:
            return vwap

        typical_price = (highs + lows + closes) / 3.0
        cum_tp_vol = np.cumsum(typical_price * volumes)
        cum_vol = np.cumsum(volumes)

        # Avoid division by zero
        mask = cum_vol > 0
        vwap[mask] = cum_tp_vol[mask] / cum_vol[mask]

        return vwap

    @staticmethod
    def detect_regime(
        sma20: np.ndarray,
        sma50: np.ndarray,
        adx: np.ndarray,
    ) -> str:
        """
        Detect the current market regime.
        Returns: 'TREND', 'RANGE', or 'EVENT'
        """
        # Handle both scalar and array inputs
        def _latest_valid(val):
            if isinstance(val, (int, float, np.floating)):
                return None if np.isnan(val) else float(val)
            arr = np.asarray(val)
            if arr.ndim == 0:
                return None if np.isnan(arr) else float(arr)
            for v in reversed(arr):
                if not np.isnan(v):
                    return float(v)
            return None

        latest_adx = _latest_valid(adx)
        latest_sma20 = _latest_valid(sma20)
        latest_sma50 = _latest_valid(sma50)

        if latest_adx is None or latest_sma20 is None or latest_sma50 is None:
            return "RANGE"

        if latest_adx > 25:
            return "TREND"
        else:
            return "RANGE"
