"""Microstructure primitives for fakeout (false-breakout) detection and
capital-safety exits.

═══════════════════════════════════════════════════════════════════════════════
IMPORTANT — every numeric default in this module is an UNVALIDATED PLACEHOLDER.
═══════════════════════════════════════════════════════════════════════════════
The gates below (order-book-imbalance threshold, volume multiple, CVD-divergence
sensitivity, bid-liquidity-crash ratio, hold-time limits) are *provisional priors*
copied from public rules-of-thumb. They are NOT measured facts for FX / oil /
crypto, and they have never been validated on this account's instruments.

They exist only so the *mechanism* can run and be A/B-compared offline. Precision
comes in Step 2, after calibrating on real 2024-2026 event history. Do NOT treat
any number in this file as ground truth — treat it as a knob to be tuned later.

Design rules:
  - Pure functions, no side effects, no I/O.
  - Every function degrades safely to "cannot tell" (None / False) when the input
    data (Level-2 sizes, trade tape) is missing, so a model without a real order
    book is never *blocked* by a gate it has no data to evaluate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


# ── provisional, UNVALIDATED default thresholds ──────────────────────────────
# See module docstring: placeholders only, to be calibrated on real data (Step 2).
@dataclass(frozen=True)
class FakeoutConfig:
    """Entry-side false-breakout gate parameters (all provisional placeholders)."""
    min_obi_abs: float = 0.40          # |OBI| the breakout side must show to be "real"
    min_volume_mult: float = 5.0       # breakout-bar volume vs recent average
    levels: int = 5                    # order-book depth levels to aggregate


@dataclass(frozen=True)
class CapitalSafetyExitConfig:
    """Exit-side capital-safety parameters (all provisional placeholders)."""
    cvd_divergence_lookback: int = 10  # bars to compare price extreme vs CVD extreme
    bid_crash_lookback: int = 10       # samples for the near-side resting-size baseline
    bid_crash_drop_ratio: float = 0.60 # near-side size collapse vs recent max -> flee
    max_hold_seconds: int = 1800       # hard time cap (30 min); shorten per asset later


def order_book_imbalance(
    bid_sizes: Optional[Sequence[float]],
    ask_sizes: Optional[Sequence[float]],
    levels: int = 5,
) -> Optional[float]:
    """Order Book Imbalance over the top ``levels`` of each side.

    OBI = (sum_bid - sum_ask) / (sum_bid + sum_ask), in [-1, +1].
      +1  = all resting size is on the bid (strong buy support)
      -1  = all resting size is on the ask (offers stacked above; thin support)

    Returns ``None`` when sizes are missing or sum to zero, so a caller with no
    Level-2 feed can decline to judge rather than be forced into a verdict.
    """
    if not bid_sizes or not ask_sizes:
        return None
    bids = [float(s) for s in list(bid_sizes)[:levels] if s is not None and float(s) >= 0.0]
    asks = [float(s) for s in list(ask_sizes)[:levels] if s is not None and float(s) >= 0.0]
    if not bids or not asks:
        return None
    total_bid = sum(bids)
    total_ask = sum(asks)
    denom = total_bid + total_ask
    if denom <= 0.0:
        return None
    return (total_bid - total_ask) / denom


def is_breakout_fakeout(
    direction: str,
    obi: Optional[float],
    config: FakeoutConfig = FakeoutConfig(),
    volume_mult: Optional[float] = None,
) -> Tuple[bool, str]:
    """Judge whether a *directional breakout* is unsupported by the book/tape and
    therefore likely a fakeout (false冲击).

    Logic (placeholder thresholds):
      - LONG breakout is real only if OBI >= +min_obi_abs (real bids underneath).
      - SHORT breakout is real only if OBI <= -min_obi_abs (real offers on top).
      - Optionally require breakout-bar volume >= min_volume_mult * average.

    Returns ``(is_fakeout, reason)``. When OBI is unavailable it returns
    ``(False, "obi_unavailable")`` — i.e. do NOT block a trade we cannot judge.
    """
    d = (direction or "").upper()
    if obi is None:
        return False, "obi_unavailable"
    if volume_mult is not None and volume_mult < config.min_volume_mult:
        return True, f"fakeout_volume_too_low_{volume_mult:.2f}x<{config.min_volume_mult:.2f}x"
    if d in ("LONG", "BUY"):
        if obi < config.min_obi_abs:
            return True, f"fakeout_obi_weak_bid_{obi:.2f}<{config.min_obi_abs:.2f}"
        return False, f"breakout_supported_obi_{obi:.2f}"
    if d in ("SHORT", "SELL"):
        if obi > -config.min_obi_abs:
            return True, f"fakeout_obi_weak_ask_{obi:.2f}>-{config.min_obi_abs:.2f}"
        return False, f"breakout_supported_obi_{obi:.2f}"
    return False, "direction_flat_or_unknown"


def cumulative_volume_delta(
    prices: Sequence[float],
    volumes: Sequence[float],
) -> List[float]:
    """Cumulative Volume Delta via the tick rule.

    Without a real aggressor flag we infer it from price change: an up-tick counts
    the bar's volume as aggressive buying (+), a down-tick as aggressive selling
    (-), an unchanged tick carries the previous sign (0 on the first bar). The
    running sum is the CVD series (same length as inputs).
    """
    n = min(len(prices), len(volumes))
    cvd: List[float] = []
    running = 0.0
    sign = 0
    for i in range(n):
        if i > 0:
            if prices[i] > prices[i - 1]:
                sign = 1
            elif prices[i] < prices[i - 1]:
                sign = -1
            # else: keep previous sign (flat tick)
        running += sign * float(volumes[i])
        cvd.append(running)
    return cvd


def cvd_top_divergence(
    prices: Sequence[float],
    cvd: Sequence[float],
    direction: str,
    lookback: int = 10,
) -> Tuple[bool, str]:
    """Detect price/CVD divergence that says "the move is being distributed into".

    For a LONG: price makes a higher high over ``lookback`` but CVD makes a lower
    high → aggressive buyers are drying up while price floats → bearish top
    divergence → take profit before the reversal (见好就收). SHORT is mirrored.

    Returns ``(is_divergent, reason)``; ``(False, "insufficient_data")`` when the
    tape is too short to judge.
    """
    d = (direction or "").upper()
    n = min(len(prices), len(cvd))
    if n < max(3, lookback // 2 + 1):
        return False, "insufficient_data"
    window_p = list(prices)[-lookback:]
    window_c = list(cvd)[-lookback:]
    half = max(1, len(window_p) // 2)
    prev_p, recent_p = window_p[:half], window_p[half:]
    prev_c, recent_c = window_c[:half], window_c[half:]
    if d in ("LONG", "BUY"):
        price_hh = max(recent_p) > max(prev_p)
        cvd_lh = max(recent_c) < max(prev_c)
        if price_hh and cvd_lh:
            return True, "cvd_bearish_top_divergence"
        return False, "no_top_divergence"
    if d in ("SHORT", "SELL"):
        price_ll = min(recent_p) < min(prev_p)
        cvd_hl = min(recent_c) > min(prev_c)
        if price_ll and cvd_hl:
            return True, "cvd_bullish_bottom_divergence"
        return False, "no_bottom_divergence"
    return False, "direction_flat_or_unknown"


def near_side_liquidity_crash(
    near_side_size_series: Optional[Sequence[float]],
    lookback: int = 10,
    drop_ratio: float = 0.60,
) -> Tuple[bool, str]:
    """Detect a sudden collapse of resting size on the side you must exit into.

    For a long you exit by hitting bids; if the bid resting size collapses faster
    than ``drop_ratio`` vs its recent max, the floor is gone even before price
    drops → flee now with a market order rather than gamble on a bounce.

    Returns ``(is_crash, reason)``; safe ``(False, ...)`` on missing/short data.
    """
    if not near_side_size_series:
        return False, "size_series_unavailable"
    series = [float(s) for s in near_side_size_series if s is not None and float(s) >= 0.0]
    if len(series) < max(2, lookback // 2 + 1):
        return False, "insufficient_data"
    window = series[-lookback:]
    recent_max = max(window)
    current = series[-1]
    if recent_max <= 0.0:
        return False, "no_baseline_liquidity"
    remaining = current / recent_max
    if remaining <= (1.0 - drop_ratio):
        return True, f"bid_liquidity_crash_{remaining:.2f}_of_max"
    return False, f"liquidity_ok_{remaining:.2f}_of_max"
