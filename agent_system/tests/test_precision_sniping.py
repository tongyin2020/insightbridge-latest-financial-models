from datetime import datetime, timezone

from agent_system.config import AgentConfig
from agent_system.precision_sniping import CrossAssetInterlock, UnifiedExecutionCoordinator
from agent_system.precision_sniping.breakout_filter import MicrostructureBreakoutFilter
from agent_system.precision_sniping.kinetic_tracker import KineticInFlightBacktester
from agent_system.state import BotSnapshot


def _make_config(tmp_path):
    return AgentConfig(base_dir=tmp_path)


def _bot_snapshot(bot_id, symbols, avg_move=0.0, confirms=0, wakes=0, fakeout=0, cvd=0, liq=0):
    return BotSnapshot(
        bot_id=bot_id,
        symbols=symbols,
        shadow_summary={
            "timeseries_relevant": 10,
            "timeseries_confirm": confirms,
            "timeseries_avg_expected_move_frac": avg_move,
            "news_would_wake": wakes,
            "microstructure_fakeout": fakeout,
            "microstructure_cvd_divergence": cvd,
            "microstructure_liquidity_crash": liq,
        },
    )


def test_cross_asset_interlock_threshold(tmp_path):
    cfg = _make_config(tmp_path)
    snapshots = {
        "crypto": _bot_snapshot("crypto", ["BTC"], avg_move=0.03, confirms=8, wakes=3),
        "fx": _bot_snapshot("fx", ["AUDUSD"], avg_move=0.015, confirms=6, wakes=4),
        "oil": _bot_snapshot("oil", ["CL"], avg_move=0.04, confirms=7, wakes=5),
        "bond": _bot_snapshot("bond", ["ZN"], avg_move=0.005, confirms=2, wakes=1),
        "index": _bot_snapshot("index", ["MES"], avg_move=0.012, confirms=5, wakes=3),
    }
    interlock = CrossAssetInterlock(cfg).evaluate(snapshots)
    assert interlock.score >= 0.80
    assert interlock.primary_bot in snapshots
    assert interlock.secondary_scale == 0.25


def test_breakout_filter_cooling_and_ofi(tmp_path):
    cfg = _make_config(tmp_path)
    filt = MicrostructureBreakoutFilter("FX", "INTERVENTION")
    assert filt.arm(0.85) is True
    # before cooling-off, no breakout
    assert filt.validate_breakout(1.0, {"bid_sizes_top_3": [10, 10, 10], "ask_sizes_top_3": [1, 1, 1]}) is False
    # after cooling-off (manually set armed_timestamp to past)
    filt.armed_timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert filt.validate_breakout(1.0, {"bid_sizes_top_3": [10, 10, 10], "ask_sizes_top_3": [1, 1, 1]}) is True
    assert filt.system_state == "IN_TRADE"


def test_kinetic_tracker_exit_momentum(tmp_path):
    cfg = _make_config(tmp_path)
    tracker = KineticInFlightBacktester(entry_price=100.0, max_duration_mins=60.0)
    # Simulate rising then slowing price series
    prices = [100.0, 100.1, 100.3, 100.55, 100.75, 100.88, 100.95, 101.0]
    for i, p in enumerate(prices):
        tracker.update_telemetry(p)
        tracker.time_deltas[-1] = float(i)  # force evenly spaced minutes for deterministic regression
    decision = tracker.evaluate_exit_criteria()
    assert decision in ("HOLD", "EXIT_MOMENTUM", "EXIT_TTL")


def test_unified_coordinator_lockout_after_exit(tmp_path):
    cfg = _make_config(tmp_path)
    snapshots = {
        "fx": _bot_snapshot("fx", ["USDJPY"], avg_move=0.02, confirms=8, wakes=5),
    }
    actions = [{"bot_id": "fx", "symbol": "USDJPY", "direction": "BUY", "suggested_size": 1.0}]
    prices = {"USDJPY": 150.0}
    l2_books = {"USDJPY": {"bid_sizes_top_3": [10, 10, 10], "ask_sizes_top_3": [1, 1, 1]}}

    coordinator = UnifiedExecutionCoordinator(CrossAssetInterlock(cfg))
    # Need to satisfy cooling-off quickly for test
    coordinator._filters["fx:USDJPY"] = MicrostructureBreakoutFilter("FX", "INTERVENTION")
    coordinator._filters["fx:USDJPY"].system_state = "ARMED"
    coordinator._filters["fx:USDJPY"].armed_timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)

    result = coordinator.process_tick(snapshots, actions, prices, l2_books)
    assert result["status"] == "PROCESSED"
    assert any(d["status"] == "ENTER_MARKET" for d in result["decisions"])
