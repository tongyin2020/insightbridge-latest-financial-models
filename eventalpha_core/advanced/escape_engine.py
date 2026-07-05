from __future__ import annotations

from dataclasses import dataclass
from typing import List

from eventalpha_core.schema import DecisionAction, PositionState
from eventalpha_core.advanced.measured_timing import measured_time_stop
from eventalpha_core.advanced.microstructure import (
    CapitalSafetyExitConfig,
    cumulative_volume_delta,
    cvd_top_divergence,
    near_side_liquidity_crash,
)


@dataclass
class EscapeSignal:
    action: DecisionAction
    urgency: int
    reduce_fraction: float
    score: float
    reasons: List[str]


def _microstructure_exit_score(
    pos: PositionState, config: CapitalSafetyExitConfig
) -> tuple[float, List[str], bool]:
    """Capital-safety exit contributions from tape/book carried on ``pos.raw``.

    Reads optional ``recent_prices`` + ``recent_volumes`` (or ``cvd_series``) and
    ``near_side_size_series``. Each degrades to a no-op when its data is absent, so
    a position without a Level-2/tape feed is never force-exited by a gate it
    cannot evaluate. Returns ``(score, reasons, force_exit)`` where ``force_exit``
    means a bid/ask-side liquidity collapse => flee now (capital safety first).
    Thresholds are UNVALIDATED placeholders pending Step-2 calibration.
    """
    raw = pos.raw or {}
    score = 0.0
    reasons: List[str] = []
    force_exit = False
    direction = pos.direction.value

    cvd_series = raw.get("cvd_series")
    recent_prices = raw.get("recent_prices")
    if cvd_series is None and recent_prices is not None and raw.get("recent_volumes") is not None:
        cvd_series = cumulative_volume_delta(recent_prices, raw.get("recent_volumes"))
    if recent_prices is not None and cvd_series is not None:
        diverged, why = cvd_top_divergence(
            recent_prices, cvd_series, direction, config.cvd_divergence_lookback
        )
        if diverged:
            score += 0.30
            reasons.append(f"cvd_divergence:{why}")

    crash, why = near_side_liquidity_crash(
        raw.get("near_side_size_series"),
        config.bid_crash_lookback,
        config.bid_crash_drop_ratio,
    )
    if crash:
        score += 0.60
        force_exit = True
        reasons.append(f"liquidity_crash:{why}")

    if pos.seconds_in_trade > config.max_hold_seconds:
        score += 0.20
        reasons.append(f"hard_hold_cap(>{config.max_hold_seconds}s)")
    return score, reasons, force_exit


def escape_decision(
    pos: PositionState,
    mfe_r_multiple: float = 0.0,
    current_r_multiple: float = 0.0,
    microstructure_exit_enabled: bool = False,
    exit_config: CapitalSafetyExitConfig = CapitalSafetyExitConfig(),
) -> EscapeSignal:
    """Sensitive exit engine. Exit should be faster than entry.

    Designed for event trades where original thesis can decay quickly. When
    ``microstructure_exit_enabled`` is set, capital-safety exits (CVD top
    divergence, near-side liquidity crash, hard hold cap) are added on top of the
    legacy thesis-decay exits. Default OFF -> byte-for-byte unchanged behaviour.
    """
    reasons = []
    score = 0.0
    confidence_decay = max(0.0, pos.confidence_at_entry - pos.confidence_now)
    if confidence_decay > 0.12:
        score += 0.25
        reasons.append(f"confidence_decay={confidence_decay:.2f}")
    if pos.news_alignment < 0.42:
        score += 0.25
        reasons.append(f"news_contradiction={pos.news_alignment:.2f}")
    if pos.cross_asset_alignment < 0.42:
        score += 0.22
        reasons.append(f"cross_asset_breakdown={pos.cross_asset_alignment:.2f}")
    if pos.reversal_score > 0.62:
        score += 0.20
        reasons.append(f"reversal_score={pos.reversal_score:.2f}")
    if pos.spread_bps > 30:
        score += 0.18
        reasons.append(f"spread_widening={pos.spread_bps:.1f}bps")
    if mfe_r_multiple > 1.0 and current_r_multiple < 0.60 * mfe_r_multiple:
        score += 0.22
        reasons.append(f"profit_giveback: mfe={mfe_r_multiple:.2f}R now={current_r_multiple:.2f}R")
    time_stop = measured_time_stop(pos.asset, default=1800)
    if pos.seconds_in_trade > time_stop and pos.momentum_score < 0.52:
        score += 0.12
        reasons.append(f"time_decay_without_momentum(>{time_stop}s)")
    force_exit = False
    if microstructure_exit_enabled:
        ms_score, ms_reasons, force_exit = _microstructure_exit_score(pos, exit_config)
        score += ms_score
        reasons.extend(ms_reasons)
    score = min(1.0, score)
    if force_exit:
        return EscapeSignal(DecisionAction.EXIT, 5, 1.0, score, reasons)
    if score >= 0.58:
        return EscapeSignal(DecisionAction.EXIT, 5, 1.0, score, reasons)
    if score >= 0.38:
        return EscapeSignal(DecisionAction.REDUCE, 4, 0.50, score, reasons)
    if score >= 0.22:
        return EscapeSignal(DecisionAction.REDUCE, 3, 0.25, score, reasons)
    return EscapeSignal(DecisionAction.WATCH, 1, 0.0, score, reasons or ["exit_conditions_not_met"])
