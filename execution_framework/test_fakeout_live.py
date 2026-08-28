"""Offline self-check for the live right-side engine's fakeout (false-breakout) gate.

Data-free and deterministic: builds a synthetic bullish-breakout bar series and a
seeded event state, then drives the real `RightSideEventEngine.evaluate()` path to
prove the OBI fakeout gate:
  * gate OFF                       -> inert (BUY, OBI only reported),
  * gate ON  + book backs breakout -> BUY,
  * gate ON  + book contradicts    -> REJECT (fakeout),
  * gate ON  + no Level-2 sizes    -> BUY (never blocks a trade it can't judge).

The OBI threshold itself is an unvalidated placeholder (see microstructure.py);
this test asserts the WIRING, not that 0.40 is the "right" number.

Run: python3 execution_framework/test_fakeout_live.py
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
    rows = []
    p = BAND
    for i in range(n - 1):
        o = p
        c = p + (5 if i % 2 == 0 else -5)
        rows.append([o, max(o, c) + 3, min(o, c) - 3, c, 100.0])
        p = c
    rows.append([BAND - 2, FINAL_CLOSE + 2, BAND - 4, FINAL_CLOSE, 200.0])
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])


def _evaluate(fakeout: bool, bid_sizes=None, ask_sizes=None, symbol: str = "BTC",
              require_book: bool = False):
    eng = RightSideEventEngine(fakeout_filter_enabled=fakeout,
                               fakeout_require_book=require_book)
    now = datetime.now(timezone.utc)
    eng.states[symbol] = EventState(
        symbol=symbol, event_name="unit_cpi", event_time=now - timedelta(minutes=30),
        base_atr=10.0, peak_atr=100.0, event_price=FINAL_CLOSE, active=True,
    )
    return eng.evaluate(symbol, now, _breakout_df(), bid=FINAL_CLOSE - 1,
                        ask=FINAL_CLOSE + 1, bid_sizes=bid_sizes, ask_sizes=ask_sizes)


def test_gate_off_is_inert():
    out = _evaluate(False, bid_sizes=[1, 1], ask_sizes=[50, 50])  # contradicting book
    assert out["status"] == "BUY", out
    assert out["fakeout_filter_enabled"] is False
    assert out["obi"] is not None            # reported for audit even when off
    print("✓ fakeout gate OFF -> BUY (OBI reported, not enforced)")


def test_supported_breakout_trades():
    out = _evaluate(True, bid_sizes=[80, 60, 40], ask_sizes=[5, 3, 2])  # strong bids
    assert out["status"] == "BUY", out
    assert out["obi"] > 0.4
    print(f"✓ book-backed breakout + gate ON -> BUY (OBI={out['obi']:.2f})")


def test_contradicting_book_rejected_as_fakeout():
    out = _evaluate(True, bid_sizes=[2, 1, 1], ask_sizes=[60, 40, 30])  # offers stacked
    assert out["status"] == "REJECT", out
    assert "fakeout_obi_weak_bid" in out["reason"], out
    print(f"✓ unsupported breakout + gate ON -> REJECT ({out['reason']})")


def test_no_level2_never_blocks():
    out = _evaluate(True, bid_sizes=None, ask_sizes=None)  # no book available
    assert out["status"] == "BUY", out
    assert out["obi"] is None
    assert out["fakeout_reason"] == "obi_unavailable"
    print("✓ no Level-2 sizes + gate ON -> BUY (never blocks unjudgeable trade)")


def test_strict_mode_blocks_when_level2_is_missing():
    out = _evaluate(True, bid_sizes=None, ask_sizes=None, require_book=True)
    assert out["status"] == "HOLD", out
    assert out["reason"] == "fakeout_book_required_but_unavailable", out
    print("✓ strict fakeout mode + no Level-2 -> HOLD (fail closed)")


def main() -> int:
    test_gate_off_is_inert()
    test_supported_breakout_trades()
    test_contradicting_book_rejected_as_fakeout()
    test_no_level2_never_blocks()
    test_strict_mode_blocks_when_level2_is_missing()
    print("\n✅ live fakeout gate self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
