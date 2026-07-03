"""V2 decision orchestrator: single entry point for the v2 gate chain.

    Opportunity -> Risk -> Execution Quality -> Expected Value -> ENTER

Every rejection is attributed to a specific gate. This does NOT replace
``EventAlphaBrain.decide`` and is not wired into the live path in Phase 1;
callers opt in explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .opportunity_engine import OpportunityEngine
from .risk_gate import RiskGate
from .expected_value_engine import ExpectedValueEngine
from .execution_quality_gate import ExecutionQualityGate
from .cost_model import CostModel, default_cost_model
from .audit_logger import V2AuditLogger


@dataclass
class V2Decision:
    action: str            # NO_TRADE | ENTER_SMALL | ENTER_NORMAL
    direction: str
    size_multiplier: float
    confidence: float
    expected_value_bps: float
    reason: str
    rejected_by: Optional[str] = None


class V2DecisionOrchestrator:
    def __init__(self, opportunity=None, risk=None, ev=None, execution=None):
        self.opportunity = opportunity or OpportunityEngine()
        self.risk = risk or RiskGate()
        self.ev = ev or ExpectedValueEngine()
        self.execution = execution or ExecutionQualityGate()

    def decide(self, event, state, account_state=None, execution_state=None,
               cost_model: Optional[CostModel] = None,
               secs_since_t0: float = 0.0) -> V2Decision:
        opp = self.opportunity.evaluate(state, event)
        if not opp.should_consider:
            return V2Decision("NO_TRADE", "none", 0.0, opp.confidence, 0.0,
                              "opportunity rejected: " + opp.reason, "opportunity")

        risk = self.risk.evaluate(state, account_state)
        if not risk.allowed:
            return V2Decision("NO_TRADE", "none", 0.0, opp.confidence, 0.0,
                              "risk rejected: " + risk.reason, "risk")

        if execution_state is not None:
            exe = self.execution.evaluate(execution_state)
            if not exe.allowed:
                return V2Decision("NO_TRADE", "none", 0.0, opp.confidence, 0.0,
                                  "execution rejected: " + exe.reason, "execution")
            execution_size = exe.quality_score
        else:
            execution_size = 1.0

        if cost_model is None:
            cost_model = default_cost_model(getattr(state, "asset", "FX"))
        ev = self.ev.estimate(opp, state, cost_model, secs_since_t0=secs_since_t0)
        if not ev.tradable:
            return V2Decision("NO_TRADE", "none", 0.0, opp.confidence, ev.ev_bps,
                              "EV rejected: " + ev.reason, "expected_value")

        size = min(risk.max_size_multiplier, execution_size)
        if ev.ev_bps < 2.0:
            size *= 0.5
        if opp.confidence < 0.65:
            size *= 0.5
        action = "ENTER_SMALL" if size < 0.75 else "ENTER_NORMAL"
        reason = f"{opp.reason} | {risk.reason} | {ev.reason}"
        return V2Decision(action, opp.direction, round(size, 2), opp.confidence,
                          ev.ev_bps, reason, None)


def decide_v2(event, state, account_state=None, execution_state=None,
              cost_model: Optional[CostModel] = None, secs_since_t0: float = 0.0,
              audit: Optional[V2AuditLogger] = None) -> V2Decision:
    """Convenience wrapper: run the v2 stack once, optionally audit-logging it."""
    orch = V2DecisionOrchestrator()
    decision = orch.decide(event, state, account_state, execution_state,
                           cost_model, secs_since_t0)
    if audit is not None:
        audit.log(getattr(state, "symbol", "?"), decision)
    return decision
