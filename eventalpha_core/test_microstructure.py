"""Offline, data-free self-check for the microstructure primitives.

Deterministic: no market data needed. Asserts the mechanics of OBI, fakeout
judgement, CVD, CVD divergence, and near-side liquidity crash — AND the critical
safety property that every gate degrades to "cannot tell" (never blocks) when its
input data is missing. The numeric thresholds themselves are unvalidated
placeholders (see microstructure.py docstring); this test does not assert they
are "correct", only that the logic wires them through as intended.

Run: python3 eventalpha_core/test_microstructure.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eventalpha_core.advanced.escape_engine import escape_decision
from eventalpha_core.advanced.microstructure import (
    CapitalSafetyExitConfig,
    FakeoutConfig,
    cumulative_volume_delta,
    cvd_top_divergence,
    is_breakout_fakeout,
    near_side_liquidity_crash,
    order_book_imbalance,
)
from eventalpha_core.schema import AssetClass, DecisionAction, Direction, PositionState


def _healthy_long_position(seconds_in_trade: int = 60, raw: dict | None = None) -> PositionState:
    """A position whose LEGACY exit score is 0 (nothing wrong), so any exit that
    fires must come from the microstructure gates under test."""
    return PositionState(
        asset=AssetClass.CRYPTO, symbol="BTC", direction=Direction.LONG,
        entry_price=100.0, current_price=101.0,
        max_price_since_entry=101.0, min_price_since_entry=100.0,
        seconds_in_trade=seconds_in_trade,
        confidence_at_entry=0.70, confidence_now=0.70, spread_bps=5.0,
        momentum_score=0.70, reversal_score=0.30,
        cross_asset_alignment=0.70, news_alignment=0.70,
        raw=raw or {},
    )


def test_obi_basic_and_bounds():
    assert order_book_imbalance([10, 0, 0], [0, 0, 0]) == 1.0        # all bid
    assert order_book_imbalance([0, 0, 0], [10, 0, 0]) == -1.0       # all ask
    assert abs(order_book_imbalance([5, 5], [5, 5]) - 0.0) < 1e-9    # balanced
    obi = order_book_imbalance([30, 10], [10, 0])                    # bid-heavy
    assert 0.0 < obi <= 1.0
    print("✓ OBI computes in [-1,1] with correct sign")


def test_obi_missing_data_returns_none():
    assert order_book_imbalance(None, [1, 2]) is None
    assert order_book_imbalance([1, 2], None) is None
    assert order_book_imbalance([0, 0], [0, 0]) is None              # zero book
    print("✓ OBI returns None on missing/empty book (cannot tell)")


def test_fakeout_long_short():
    cfg = FakeoutConfig(min_obi_abs=0.40)
    # LONG with weak bid support -> fakeout
    is_fake, reason = is_breakout_fakeout("LONG", obi=0.10, config=cfg)
    assert is_fake and "obi_weak_bid" in reason
    # LONG with strong bid support -> real
    is_fake, _ = is_breakout_fakeout("LONG", obi=0.55, config=cfg)
    assert not is_fake
    # SHORT with strong ask stack -> real
    is_fake, _ = is_breakout_fakeout("SHORT", obi=-0.55, config=cfg)
    assert not is_fake
    # SHORT with weak ask -> fakeout
    is_fake, reason = is_breakout_fakeout("SHORT", obi=-0.10, config=cfg)
    assert is_fake and "obi_weak_ask" in reason
    print("✓ fakeout judged for both directions using OBI gate")


def test_fakeout_unavailable_never_blocks():
    is_fake, reason = is_breakout_fakeout("LONG", obi=None)
    assert is_fake is False and reason == "obi_unavailable"
    print("✓ fakeout gate never blocks when OBI is unavailable")


def test_fakeout_volume_gate():
    cfg = FakeoutConfig(min_obi_abs=0.40, min_volume_mult=5.0)
    is_fake, reason = is_breakout_fakeout("LONG", obi=0.9, config=cfg, volume_mult=2.0)
    assert is_fake and "volume_too_low" in reason
    print("✓ fakeout gate rejects thin-volume breakout even with good OBI")


def test_cvd_tick_rule():
    prices = [100, 101, 102, 101, 101]
    vols = [10, 10, 10, 10, 10]
    cvd = cumulative_volume_delta(prices, vols)
    # first bar sign 0 (+0), up, up, down, flat(carry -1)
    assert cvd == [0.0, 10.0, 20.0, 10.0, 0.0]
    print("✓ CVD tick-rule accumulates signed volume")


def test_cvd_top_divergence_long():
    # price grinds to a higher high, but CVD rolls over (lower high) -> divergence
    prices = [100, 101, 102, 103, 104, 103, 104, 105, 106, 107]
    cvd    = [0,   5,   9,   12,  14,  13,  12,  11,  10,  9]
    is_div, reason = cvd_top_divergence(prices, cvd, "LONG", lookback=10)
    assert is_div and reason == "cvd_bearish_top_divergence"
    print("✓ CVD top divergence flags distribution on a rising price")


def test_cvd_divergence_insufficient_data():
    is_div, reason = cvd_top_divergence([1, 2], [1, 2], "LONG", lookback=10)
    assert is_div is False and reason == "insufficient_data"
    print("✓ CVD divergence safe on short tape")


def test_liquidity_crash():
    # near-side bid size collapses from ~100 to 20 (80% gone) -> crash
    sizes = [100, 98, 95, 90, 88, 85, 80, 70, 40, 20]
    is_crash, reason = near_side_liquidity_crash(sizes, lookback=10, drop_ratio=0.60)
    assert is_crash and "bid_liquidity_crash" in reason
    # steady book -> no crash
    steady = [100, 99, 101, 100, 98, 102, 100, 99, 101, 100]
    is_crash, _ = near_side_liquidity_crash(steady, lookback=10, drop_ratio=0.60)
    assert not is_crash
    print("✓ near-side liquidity crash detected vs recent max")


def test_liquidity_crash_missing_data_safe():
    assert near_side_liquidity_crash(None)[0] is False
    assert near_side_liquidity_crash([1.0])[0] is False
    print("✓ liquidity-crash gate safe on missing/short data")


def test_escape_default_off_is_inert():
    # crash data present, but the gate is OFF -> legacy behaviour (no exit).
    crash = [100, 98, 95, 90, 85, 80, 70, 50, 30, 15]
    pos = _healthy_long_position(raw={"near_side_size_series": crash})
    sig_off = escape_decision(pos)  # default microstructure_exit_enabled=False
    assert sig_off.action == DecisionAction.WATCH
    print("✓ escape engine inert when microstructure exits OFF (default)")


def test_escape_liquidity_crash_forces_exit_when_on():
    crash = [100, 98, 95, 90, 85, 80, 70, 50, 30, 15]
    pos = _healthy_long_position(raw={"near_side_size_series": crash})
    sig = escape_decision(pos, microstructure_exit_enabled=True)
    assert sig.action == DecisionAction.EXIT and sig.urgency == 5
    assert any("liquidity_crash" in r for r in sig.reasons)
    print("✓ liquidity crash forces immediate EXIT (capital safety) when ON")


def test_escape_cvd_divergence_contributes_when_on():
    prices = [100, 101, 102, 103, 104, 103, 104, 105, 106, 107]
    # engineer CVD lower-high vs price higher-high via a declining-sign tape
    cvd = [0, 5, 9, 12, 14, 13, 12, 11, 10, 9]
    pos = _healthy_long_position(raw={"recent_prices": prices, "cvd_series": cvd})
    sig = escape_decision(pos, microstructure_exit_enabled=True)
    assert any("cvd_divergence" in r for r in sig.reasons)
    assert sig.action in (DecisionAction.REDUCE, DecisionAction.EXIT)
    print("✓ CVD divergence contributes to exit score when ON")


def test_escape_no_microstructure_data_is_safe_when_on():
    pos = _healthy_long_position(raw={})  # no tape/book carried
    sig = escape_decision(pos, microstructure_exit_enabled=True)
    assert sig.action == DecisionAction.WATCH  # never force-exits on absent data
    print("✓ microstructure exits never fire on absent data (never blocks)")


def test_hard_hold_cap_forces_exit_by_itself():
    pos = _healthy_long_position(seconds_in_trade=1800, raw={})
    sig = escape_decision(pos, microstructure_exit_enabled=True)
    assert sig.action == DecisionAction.EXIT and sig.urgency == 5
    assert any("hard_hold_cap" in r for r in sig.reasons)
    print("✓ hard hold cap alone forces immediate EXIT")


def test_hard_cap_delegated_to_lifecycle_monitor():
    """When the caller passes hard_cap_breached explicitly, the lifecycle
    monitor's verdict is authoritative and the config clock is ignored."""
    # (a) monitor says cap breached, even though config clock has NOT elapsed
    pos = _healthy_long_position(seconds_in_trade=60, raw={})
    sig = escape_decision(pos, microstructure_exit_enabled=True,
                          hard_cap_breached=True)
    assert sig.action == DecisionAction.EXIT and sig.urgency == 5
    assert any("hard_hold_cap" in r for r in sig.reasons)
    # (b) monitor says NOT breached, even though the config clock HAS elapsed
    #     -> this engine must not force an exit on its own clock
    pos = _healthy_long_position(seconds_in_trade=7200, raw={})
    sig = escape_decision(pos, microstructure_exit_enabled=True,
                          hard_cap_breached=False)
    assert sig.action == DecisionAction.WATCH
    assert not any("hard_hold_cap" in r for r in sig.reasons)
    print("✓ hard cap delegated to lifecycle monitor (single source of truth)")


def test_config_defaults_are_placeholders():
    # guardrail: the defaults exist and are the documented provisional priors.
    assert FakeoutConfig().min_obi_abs == 0.40
    assert CapitalSafetyExitConfig().max_hold_seconds == 1800
    print("✓ provisional placeholder configs present (to be calibrated in Step 2)")


def main() -> int:
    test_obi_basic_and_bounds()
    test_obi_missing_data_returns_none()
    test_fakeout_long_short()
    test_fakeout_unavailable_never_blocks()
    test_fakeout_volume_gate()
    test_cvd_tick_rule()
    test_cvd_top_divergence_long()
    test_cvd_divergence_insufficient_data()
    test_liquidity_crash()
    test_liquidity_crash_missing_data_safe()
    test_escape_default_off_is_inert()
    test_escape_liquidity_crash_forces_exit_when_on()
    test_escape_cvd_divergence_contributes_when_on()
    test_escape_no_microstructure_data_is_safe_when_on()
    test_hard_hold_cap_forces_exit_by_itself()
    test_hard_cap_delegated_to_lifecycle_monitor()
    test_config_defaults_are_placeholders()
    print("\n✅ microstructure self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
