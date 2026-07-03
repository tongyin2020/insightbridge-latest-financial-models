"""Execution Quality Gate: are broker/venue conditions good enough to enter?

Real costs can destroy a gross edge, so this gate stands the robot down when
quotes are stale, latency is high, the connection is down, or orders are getting
rejected. Phase 1 note: the live IBKR path does not yet emit this telemetry
(quote_age / latency / reject_rate), so until it does the gate should be fed a
real ``execution_state`` or left out (the orchestrator treats "no execution_state"
as size=1.0, i.e. it does not fabricate a pass from missing data).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionQualityResult:
    allowed: bool
    quality_score: float
    reason: str


class ExecutionQualityGate:
    def __init__(self, max_quote_age_s=2.0, max_latency_s=1.0, max_reject_rate=0.05):
        self.max_quote_age_s = max_quote_age_s
        self.max_latency_s = max_latency_s
        self.max_reject_rate = max_reject_rate

    def evaluate(self, execution_state) -> ExecutionQualityResult:
        quote_age = float(getattr(execution_state, "quote_age_s", 999.0))
        latency = float(getattr(execution_state, "latency_s", 999.0))
        reject_rate = float(getattr(execution_state, "recent_reject_rate", 1.0))
        connected = bool(getattr(execution_state, "connected", False))

        if not connected:
            return ExecutionQualityResult(False, 0.0, "broker disconnected")
        if quote_age > self.max_quote_age_s:
            return ExecutionQualityResult(False, 0.0, f"stale quote {quote_age:.2f}s")
        if latency > self.max_latency_s:
            return ExecutionQualityResult(False, 0.25, f"latency {latency:.2f}s too high")
        if reject_rate > self.max_reject_rate:
            return ExecutionQualityResult(False, 0.25, f"reject_rate {reject_rate:.2%} too high")

        quality = max(0.0, min(1.0,
            1.0 - 0.35 * latency / self.max_latency_s
            - 0.35 * quote_age / self.max_quote_age_s
            - 0.30 * reject_rate / self.max_reject_rate))
        return ExecutionQualityResult(True, quality, f"execution quality ok: {quality:.2f}")
