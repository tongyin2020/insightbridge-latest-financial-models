"""Risk Gate: hard risk filter. Risk dominates signal quality.

If real-time execution or market risk is unacceptable, the system must not trade
even when the opportunity score is high. Limits are safety boundaries and are
intended to be human-set constants, never relaxed by the AI (see parameter
governance in the v2 report).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskResult:
    allowed: bool
    risk_level: str
    max_size_multiplier: float
    reason: str


class RiskGate:
    def __init__(self, max_spread_bps=3.0, max_reversal=0.65, min_liquidity=0.45,
                 max_daily_loss_bps=100.0, min_execution_quality=0.45):
        self.max_spread_bps = max_spread_bps
        self.max_reversal = max_reversal
        self.min_liquidity = min_liquidity
        self.max_daily_loss_bps = max_daily_loss_bps
        self.min_execution_quality = min_execution_quality

    def evaluate(self, state, account_state=None) -> RiskResult:
        spread = float(getattr(state, "spread_bps", 999.0))
        reversal = float(getattr(state, "reversal_score", 1.0))
        liquidity = float(getattr(state, "liquidity_score", 0.0))
        volatility_z = float(getattr(state, "volatility_z", 1.0))
        execution = float(getattr(state, "execution_quality", 0.0))
        daily_loss = float(getattr(account_state, "daily_loss_bps", 0.0)) if account_state else 0.0

        failures = []
        if spread > self.max_spread_bps:
            failures.append(f"spread {spread:.2f}>{self.max_spread_bps:.2f}")
        if reversal > self.max_reversal:
            failures.append(f"reversal {reversal:.2f}>{self.max_reversal:.2f}")
        if liquidity < self.min_liquidity:
            failures.append(f"liquidity {liquidity:.2f}<{self.min_liquidity:.2f}")
        if daily_loss <= -abs(self.max_daily_loss_bps):
            failures.append(f"daily_loss {daily_loss:.1f} exceeds limit")
        if execution < self.min_execution_quality:
            failures.append(f"execution_quality {execution:.2f}<{self.min_execution_quality:.2f}")
        if failures:
            return RiskResult(False, "HIGH", 0.0, "; ".join(failures))

        if volatility_z > 2.5 or spread > self.max_spread_bps * 0.7:
            return RiskResult(True, "MEDIUM", 0.50, "risk acceptable but size reduced")
        return RiskResult(True, "LOW", 1.00, "risk acceptable")
