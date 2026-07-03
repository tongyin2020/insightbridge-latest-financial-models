"""Dynamic Exit Engine: exit when trend quality decays or risk invalidates it.

For 10-30 minute macro repricing, overstaying is usually more dangerous than
missing a few bps, so the exit is deliberately more dynamic than the entry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str


class DynamicExitEngine:
    def __init__(self, max_hold_s=1800, min_persistence=0.45, max_reversal=0.70,
                 giveback_frac=0.40, spread_shock_bps=5.0):
        self.max_hold_s = max_hold_s
        self.min_persistence = min_persistence
        self.max_reversal = max_reversal
        self.giveback_frac = giveback_frac
        self.spread_shock_bps = spread_shock_bps

    def evaluate(self, position, state, ev_result=None) -> ExitDecision:
        hold_s = float(getattr(position, "hold_s", getattr(position, "seconds_in_trade", 0.0)))
        unrealized_bps = float(getattr(position, "unrealized_bps", 0.0))
        peak_bps = float(getattr(position, "peak_bps", max(unrealized_bps, 0.0)))
        persistence = float(getattr(state, "trend_persistence", 0.5))
        reversal = float(getattr(state, "reversal_score", 0.5))
        spread = float(getattr(state, "spread_bps", 1.0))

        if hold_s >= self.max_hold_s:
            return ExitDecision(True, "time stop reached")
        if persistence < self.min_persistence:
            return ExitDecision(True, f"trend persistence broke: {persistence:.2f}")
        if reversal > self.max_reversal:
            return ExitDecision(True, f"reversal risk high: {reversal:.2f}")
        if peak_bps > 5.0 and unrealized_bps < (1.0 - self.giveback_frac) * peak_bps:
            return ExitDecision(True, "profit giveback threshold hit")
        if ev_result is not None and float(getattr(ev_result, "ev_bps", 0.0)) < 0.0:
            return ExitDecision(True, "expected value collapsed below zero")
        if spread > self.spread_shock_bps:
            return ExitDecision(True, f"spread shock: {spread:.1f} bps")
        return ExitDecision(False, "hold")
