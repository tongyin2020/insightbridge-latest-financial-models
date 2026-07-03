"""Offline self-check for the live right-side engine's selectivity gate.

Data-free and deterministic: builds a synthetic bullish-breakout bar series and
a seeded event state, then drives the real `RightSideEventEngine.evaluate()`
path to prove:
  * gate ON  + small early move -> stand down (HOLD),
  * gate ON  + big   early move -> trades (BUY),
  * gate OFF                    -> inert (BUY, bucket only reported),
  * unmeasured asset class      -> no-op.

Run: python3 execution_framework/test_selectivity_live.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_right_side_engine import RightSideEventEngine, EventState


BAND = 60000.0
FINAL_CLOSE = BAND + 40.0


def _breakout_df(n: int = 20) -> pd.DataFrame:
    """Tight band of small bars + a final strong bullish body breakout."""
    rows = []
    p = BAND
    for i in range(n - 1):
        o = p
        c = p + (5 if i % 2 == 0 else -5)
        rows.append([o, max(o, c) + 3, min(o, c) - 3, c, 100.0])
        p = c
    # final bar: big bullish body, tiny shadows, high volume
    rows.append([BAND - 2, FINAL_CLOSE + 2, BAND - 4, FINAL_CLOSE, 200.0])
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def _engine_with_state(selectivity: bool, event_price: float,
                       symbol: str = "BTC") -> RightSideEventEngine:
    eng = RightSideEventEngine(selectivity_enabled=selectivity)
    now = datetime.now(timezone.utc)
    # Seed a state past cooldown with an established ATR peak so the ATR-decay
    # and cooldown layers pass, isolating the selectivity behaviour.
    eng.states[symbol] = EventState(
        symbol=symbol, event_name="unit_cpi", event_time=now - timedelta(minutes=30),
        base_atr=10.0, peak_atr=100.0, event_price=event_price, active=True,
    )
    return eng


def _evaluate(selectivity: bool, event_price: float, symbol: str = "BTC"):
    eng = _engine_with_state(selectivity, event_price, symbol)
    df = _breakout_df()
    now = datetime.now(timezone.utc)
    return eng.evaluate(symbol, now, df, bid=FINAL_CLOSE - 1, ask=FINAL_CLOSE + 1)


def test_baseline_signal_fires():
    # gate OFF, zero early move -> the breakout should produce a BUY (sanity that
    # the synthetic df actually clears every non-selectivity layer).
    out = _evaluate(False, FINAL_CLOSE)
    assert out["status"] == "BUY", out
    assert out["impact_bucket"] == "small"        # reported for audit
    assert out["selectivity_enabled"] is False
    print("✓ baseline breakout -> BUY (gate OFF, bucket reported)")


def test_small_impact_stands_down_when_enabled():
    out = _evaluate(True, FINAL_CLOSE)             # ~0 bps move -> small
    assert out["status"] == "HOLD", out
    assert out["reason"] == "selectivity_stand_down_small_impact", out
    assert out["impact_bucket"] == "small"
    print("✓ small early move + gate ON -> stand down (HOLD)")


def test_big_impact_trades_when_enabled():
    event_price = FINAL_CLOSE / 1.015             # final is ~+148 bps -> big
    out = _evaluate(True, event_price)
    assert out["status"] == "BUY", out
    assert out["impact_bucket"] == "big", out
    assert out["early_move_bps"] > 106.9
    print(f"✓ big early move ({out['early_move_bps']:.0f} bps) + gate ON -> BUY")


def test_unmeasured_asset_is_noop():
    eng = RightSideEventEngine(selectivity_enabled=True)
    assert eng._impact_bucket("INDEX", 500.0) is None
    assert eng._impact_bucket("TREASURY", 500.0) is None
    assert eng._impact_bucket("CRYPTO_SPOT", 500.0) == "big"
    assert eng._impact_bucket("FX", None) is None
    print("✓ unmeasured asset classes -> gate no-op; measured map through")


def main() -> int:
    test_baseline_signal_fires()
    test_small_impact_stands_down_when_enabled()
    test_big_impact_trades_when_enabled()
    test_unmeasured_asset_is_noop()
    print("\n✅ live selectivity gate self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
