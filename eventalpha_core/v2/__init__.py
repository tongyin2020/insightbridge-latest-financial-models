"""EventAlpha v2 production decision stack (opt-in, default OFF).

A simple, explainable, auditable gate chain that turns real-time market state into
a disciplined trade decision:

    Opportunity -> Risk -> Execution Quality -> Expected Value -> (enter)
    Dynamic Exit (while in a position)

Design philosophy (from the v2 upgrade report): human expertise defines the
principles, the AI evaluates real-time conditions, the robot executes with
discipline. This is NOT a data-hungry ML strategy generator; it is opportunity
detection + strict risk control + net-EV execution over the 10-30 minute macro
repricing window.

Phase 1 scope: the stack is available but is NOT wired into the live decision
path. Nothing calls it unless a caller explicitly opts in via ``decide_v2`` /
``V2DecisionOrchestrator``. Wiring, and empirical calibration of the EV numbers,
are later phases.
"""
from __future__ import annotations

from .v2_decision_orchestrator import V2DecisionOrchestrator, V2Decision, decide_v2
from .opportunity_engine import OpportunityEngine, OpportunityResult
from .risk_gate import RiskGate, RiskResult
from .expected_value_engine import ExpectedValueEngine, ExpectedValueResult
from .execution_quality_gate import ExecutionQualityGate, ExecutionQualityResult
from .dynamic_exit_engine import DynamicExitEngine, ExitDecision
from .cost_model import CostModel, default_cost_model
from .calibration import load_calibration
from .audit_logger import V2AuditLogger

__all__ = [
    "V2DecisionOrchestrator", "V2Decision", "decide_v2",
    "OpportunityEngine", "OpportunityResult",
    "RiskGate", "RiskResult",
    "ExpectedValueEngine", "ExpectedValueResult",
    "ExecutionQualityGate", "ExecutionQualityResult",
    "DynamicExitEngine", "ExitDecision",
    "CostModel", "default_cost_model",
    "load_calibration",
    "V2AuditLogger",
]
