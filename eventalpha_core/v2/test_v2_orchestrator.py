"""Deterministic, data-free self-checks for the v2 decision stack.

Run: python -m eventalpha_core.v2.test_v2_orchestrator
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

from .v2_decision_orchestrator import V2DecisionOrchestrator, decide_v2
from .cost_model import default_cost_model
from .audit_logger import V2AuditLogger
from .dynamic_exit_engine import DynamicExitEngine
from .expected_value_engine import ExpectedValueEngine
from .opportunity_engine import OpportunityEngine


@dataclass
class FakeState:
    asset: str = "FX"
    symbol: str = "EURUSD"
    spread_bps: float = 0.5
    volatility_z: float = 1.0
    momentum_score: float = 0.85
    reversal_score: float = 0.10
    liquidity_score: float = 0.85
    cross_asset_alignment: float = 0.80
    trend_persistence: float = 0.80
    execution_quality: float = 0.85
    early_move_bps: Optional[float] = 40.0
    raw: dict = field(default_factory=dict)


@dataclass
class FakeEvent:
    surprise_score: float = 0.7


@dataclass
class FakeExec:
    connected: bool = True
    quote_age_s: float = 0.3
    latency_s: float = 0.2
    recent_reject_rate: float = 0.0


@dataclass
class FakePosition:
    hold_s: float = 100.0
    unrealized_bps: float = 6.0
    peak_bps: float = 10.0


def _check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    assert cond, name


def test_strong_setup_enters():
    orch = V2DecisionOrchestrator()
    d = orch.decide(FakeEvent(), FakeState(), execution_state=FakeExec())
    _check("strong setup -> ENTER", d.action.startswith("ENTER"))
    _check("strong setup -> long", d.direction == "long")
    _check("strong setup -> positive EV", d.expected_value_bps > 0)


def test_weak_move_rejected_by_opportunity():
    weak = FakeState(momentum_score=0.5, trend_persistence=0.5, cross_asset_alignment=0.5,
                     liquidity_score=0.5, execution_quality=0.5, reversal_score=0.5)
    d = V2DecisionOrchestrator().decide(FakeEvent(surprise_score=0.0), weak,
                                        execution_state=FakeExec())
    _check("weak -> NO_TRADE", d.action == "NO_TRADE")
    _check("weak -> rejected by opportunity", d.rejected_by == "opportunity")


def test_wide_spread_rejected_by_risk():
    risky = FakeState(spread_bps=9.0)
    d = V2DecisionOrchestrator().decide(FakeEvent(), risky, execution_state=FakeExec())
    _check("wide spread -> NO_TRADE", d.action == "NO_TRADE")
    _check("wide spread -> rejected by risk", d.rejected_by == "risk")


def test_stale_quote_rejected_by_execution():
    d = V2DecisionOrchestrator().decide(FakeEvent(), FakeState(),
                                        execution_state=FakeExec(quote_age_s=9.0))
    _check("stale quote -> NO_TRADE", d.action == "NO_TRADE")
    _check("stale quote -> rejected by execution", d.rejected_by == "execution")


def test_costs_can_kill_ev():
    # crypto round-trip cost is dominated by commission; a marginal edge dies
    marginal = FakeState(asset="CRYPTO", symbol="BTCUSD", momentum_score=0.66,
                         trend_persistence=0.62, cross_asset_alignment=0.6,
                         liquidity_score=0.6, execution_quality=0.6, reversal_score=0.2,
                         spread_bps=None)  # type: ignore[arg-type]
    ev_fx = ExpectedValueEngine().estimate(
        OpportunityEngine().evaluate(FakeState(), FakeEvent()), FakeState(),
        default_cost_model("FX"))
    ev_crypto = ExpectedValueEngine().estimate(
        OpportunityEngine().evaluate(marginal, FakeEvent()), marginal,
        default_cost_model("CRYPTO"))
    _check("crypto cost > fx cost", ev_crypto.estimated_cost_bps > ev_fx.estimated_cost_bps)


def test_cost_model_round_trip():
    cm = default_cost_model("FX")
    in_window = cm.round_trip_cost_bps(secs_since_t0=0.0)
    out_window = cm.round_trip_cost_bps(secs_since_t0=999.0)
    _check("event-window cost >= normal cost", in_window >= out_window)
    _check("round trip is 2x per-side", abs(cm.round_trip_cost_bps(live_spread_bps=2.0)
           - 2.0 * (1.0 + cm.slippage_bps + cm.commission_bps)) < 1e-9)


def test_exit_time_stop_and_giveback():
    ex = DynamicExitEngine(max_hold_s=1800)
    _check("time stop exits", ex.evaluate(FakePosition(hold_s=2000.0), FakeState()).should_exit)
    give = FakePosition(hold_s=100.0, unrealized_bps=4.0, peak_bps=10.0)
    _check("giveback exits", ex.evaluate(give, FakeState()).should_exit)
    hold = FakePosition(hold_s=100.0, unrealized_bps=9.0, peak_bps=10.0)
    _check("healthy trade holds", not ex.evaluate(hold, FakeState()).should_exit)


def test_audit_logger_writes():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "v2.jsonl")
        audit = V2AuditLogger(path=path)
        decide_v2(FakeEvent(), FakeState(), execution_state=FakeExec(), audit=audit)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
        _check("audit wrote one line", len(lines) == 1)
        _check("audit line has decision", '"decision"' in lines[0])


def main():
    for fn in [test_strong_setup_enters, test_weak_move_rejected_by_opportunity,
               test_wide_spread_rejected_by_risk, test_stale_quote_rejected_by_execution,
               test_costs_can_kill_ev, test_cost_model_round_trip,
               test_exit_time_stop_and_giveback, test_audit_logger_writes]:
        print(fn.__name__)
        fn()
    print("\nALL V2 SELF-CHECKS PASSED")


if __name__ == "__main__":
    main()
