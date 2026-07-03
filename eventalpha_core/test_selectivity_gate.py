"""Offline regression test for the impact-based selectivity gate.

Data-free and deterministic (no market data needed), so it can guard the wiring
on every change. The empirical justification for the gate lives in the
eventalpha_intraday_study P&L backtest (real 2024-2025 data); this test only
asserts the brain applies the measured rule correctly and stays inert when off.

Run: python3 eventalpha_core/test_selectivity_gate.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eventalpha_core import (
    AssetClass,
    EventAlphaBrain,
    EventMemoryDB,
    EventType,
    LearningEngine,
    MacroEvent,
    MarketState,
)
from eventalpha_core.advanced.measured_timing import MEASURED_WAIT_BY_IMPACT


def _brain(selectivity: bool) -> EventAlphaBrain:
    db_path = Path(tempfile.mkdtemp()) / "mem.sqlite"
    learning = LearningEngine(EventMemoryDB(str(db_path)))
    return EventAlphaBrain(learning, max_account_risk=0.02, selectivity_enabled=selectivity)


def _event() -> MacroEvent:
    return MacroEvent(
        event_id="test_nfp",
        event_type=EventType.NFP,
        title="unit-test NFP",
        surprise_score=0.7,
        policy_score=0.5,
        source_confidence=0.8,
    )


def _state(asset: AssetClass, early_move_bps=None) -> MarketState:
    return MarketState(
        asset=asset,
        symbol="BTC" if asset == AssetClass.CRYPTO else asset.value,
        price=60000.0,
        spread_bps=5.0,
        volatility_z=1.0,
        momentum_score=0.80,
        reversal_score=0.10,
        liquidity_score=0.80,
        cross_asset_alignment=0.75,
        news_alignment=0.70,
        orderbook_pressure=0.70,
        trend_persistence=0.75,
        execution_quality=0.80,
        early_move_bps=early_move_bps,
    )


def _decide(selectivity: bool, early_move_bps, asset=AssetClass.CRYPTO):
    return _brain(selectivity).decide(_event(), _state(asset, early_move_bps))


def test_small_impact_stands_down_when_enabled():
    d = _decide(True, 10.0)  # crypto small (< 48.6)
    assert d.metadata["impact_bucket"] == "small", d.metadata
    assert d.metadata["selectivity_applied"] is True
    assert d.action.value == "watch", d.action
    assert "selectivity_stand_down_small_impact" in d.reasons
    print("✓ small impact + selectivity ON -> stand down (WATCH)")


def test_mid_and_big_adopt_impact_window_when_enabled():
    mid = _decide(True, 70.0)   # crypto mid (48.6..106.9)
    big = _decide(True, 200.0)  # crypto big (>= 106.9)
    exp_mid = MEASURED_WAIT_BY_IMPACT[(AssetClass.CRYPTO, "mid")]
    exp_big = MEASURED_WAIT_BY_IMPACT[(AssetClass.CRYPTO, "big")]
    assert mid.metadata["impact_bucket"] == "mid"
    assert mid.wait_seconds == exp_mid[0], (mid.wait_seconds, exp_mid)
    assert mid.metadata["max_wait_seconds"] == exp_mid[1]
    assert big.metadata["impact_bucket"] == "big"
    assert big.wait_seconds == exp_big[0], (big.wait_seconds, exp_big)
    assert big.metadata["max_wait_seconds"] == exp_big[1]
    assert "selectivity_stand_down_small_impact" not in big.reasons
    print(f"✓ mid/big impact + selectivity ON -> adopt window (mid min={exp_mid[0]}, big min={exp_big[0]})")


def test_disabled_is_inert():
    off = _decide(False, 10.0)  # small move but gate OFF
    assert off.metadata["selectivity_enabled"] is False
    assert off.metadata["selectivity_applied"] is False
    assert "selectivity_stand_down_small_impact" not in off.reasons
    # bucket is still reported for auditability, but no behaviour change
    assert off.metadata["impact_bucket"] == "small"
    print("✓ selectivity OFF -> gate inert (bucket reported, no stand-down/override)")


def test_no_early_move_is_noop():
    d = _decide(True, None)
    assert d.metadata["impact_bucket"] is None
    assert d.metadata["selectivity_applied"] is False
    print("✓ missing early_move_bps -> gate no-op")


def test_unmeasured_asset_is_noop():
    d = _decide(True, 200.0, asset=AssetClass.INDEX)  # INDEX has no measured edges
    assert d.metadata["impact_bucket"] is None
    assert d.metadata["selectivity_applied"] is False
    print("✓ unmeasured asset (INDEX) -> gate no-op")


def main() -> int:
    test_small_impact_stands_down_when_enabled()
    test_mid_and_big_adopt_impact_window_when_enabled()
    test_disabled_is_inert()
    test_no_early_move_is_noop()
    test_unmeasured_asset_is_noop()
    print("\n✅ selectivity gate self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
