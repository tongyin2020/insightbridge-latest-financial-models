"""Offline self-check for Step 2 · Phase A: the Level-2 depth collector and the
observe-only microstructure shadow recorder.

Data-free and deterministic: drives ``DepthCollector`` against a *fake* IB object
(duck-typed ``reqMktDepth`` / ``sleep`` / ``cancelMktDepth``) and drives
``MicrostructureShadow.observe`` on synthetic books/tapes to prove:
  * depth is parsed into bid/ask size lists and the near-side history grows,
  * broker failures degrade to (None, None) — never raise into the live loop,
  * the shadow is a strict no-op when disabled (default),
  * when enabled it records the Step-1 verdicts (fakeout / CVD divergence /
    liquidity crash) and NEVER raises,
  * absent data => obi None and every "would_*" verdict False (never blocks).

Run: python3 execution_framework/test_microstructure_shadow.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from depth_collector import DepthCollector
from microstructure_shadow import MicrostructureShadow


class _DOMLevel:
    def __init__(self, price: float, size: float) -> None:
        self.price = price
        self.size = size


class _FakeTicker:
    def __init__(self, bids, asks) -> None:
        self.domBids = bids
        self.domAsks = asks


class _FakeIB:
    def __init__(self, bids, asks, raise_on_depth: bool = False) -> None:
        self._t = _FakeTicker(bids, asks)
        self.raise_on_depth = raise_on_depth
        self.cancelled = 0

    def reqMktDepth(self, contract, numRows: int = 5):
        if self.raise_on_depth:
            raise RuntimeError("no depth subscription")
        return self._t

    def sleep(self, _seconds: float) -> None:
        pass

    def cancelMktDepth(self, contract) -> None:
        self.cancelled += 1


def _bids(sizes):
    return [_DOMLevel(100.0 - i * 0.1, s) for i, s in enumerate(sizes)]


def _asks(sizes):
    return [_DOMLevel(100.1 + i * 0.1, s) for i, s in enumerate(sizes)]


def _df(closes, vols=None):
    vols = vols or [100.0] * len(closes)
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": vols})


def test_collector_parses_depth_and_grows_history():
    col = DepthCollector(levels=3, history=10, depth_sleep=0.0)
    ib = _FakeIB(_bids([80, 60, 40]), _asks([5, 3, 2]))
    b, a = col.fetch_depth(ib, object(), "BTC")
    assert b == [80.0, 60.0, 40.0] and a == [5.0, 3.0, 2.0]
    assert ib.cancelled == 1
    # second scan with a smaller near-side -> history has two entries.
    col.fetch_depth(_FakeIB(_bids([20, 10]), _asks([5, 3])), object(), "BTC")
    assert col.near_side_size_series("BTC") == [80.0, 20.0]
    print("✓ depth collector parses Level-2 sizes and grows near-side history")


def test_collector_failure_degrades_safely():
    col = DepthCollector(depth_sleep=0.0)
    b, a = col.fetch_depth(_FakeIB([], [], raise_on_depth=True), object(), "CL")
    assert b is None and a is None  # never raises into the loop
    print("✓ depth fetch failure degrades to (None, None)")


def test_collector_tape_from_df():
    col = DepthCollector(history=5, depth_sleep=0.0)
    col.update_tape_from_df("CL", _df([1, 2, 3, 4, 5, 6, 7], [9] * 7))
    assert col.recent_prices("CL") == [3.0, 4.0, 5.0, 6.0, 7.0]  # trailing 5
    assert col.tape_source("CL") == "bar_1m"
    raw = col.raw_for_exit("CL")
    assert set(raw) == {"recent_prices", "recent_volumes",
                        "near_side_size_series", "tape_source"}
    print("✓ tape seeded from bars (trailing window, labelled bar_1m)")


def test_shadow_disabled_is_noop():
    sh = MicrostructureShadow(enabled=False)
    assert sh.observe("BTC", "long", [80, 60], [5, 3]) is None
    assert sh.n_observed == 0
    print("✓ shadow disabled -> strict no-op (default)")


def test_shadow_records_verdicts_and_logs():
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "ms.log"
        sh = MicrostructureShadow(enabled=True, log_path=str(log))

        # book backs a long breakout -> not a fakeout.
        rec = sh.observe("BTC", "long", [80, 60, 40], [5, 3, 2])
        assert rec is not None and rec["obi"] > 0.4
        assert rec["would_reject_fakeout"] is False

        # book contradicts a long breakout -> fakeout.
        rec2 = sh.observe("BTC", "long", [2, 1, 1], [60, 40, 30])
        assert rec2["would_reject_fakeout"] is True
        assert "fakeout_obi_weak_bid" in rec2["fakeout_reason"]

        # collapsing near-side bid -> liquidity crash force-exit flag.
        crash = [100, 98, 95, 90, 85, 80, 70, 50, 30, 15]
        rec3 = sh.observe("BTC", "long", [10, 8], [10, 8],
                          near_side_size_series=crash)
        assert rec3["would_force_exit_liquidity_crash"] is True

        lines = log.read_text().strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["stage"] == "microstructure_shadow"
        print("✓ shadow records fakeout / liquidity-crash verdicts and logs JSONL")


def test_shadow_absent_data_never_blocks():
    sh = MicrostructureShadow(enabled=True)
    rec = sh.observe("BTC", "long", None, None)  # no book, no tape
    assert rec is not None
    assert rec["obi"] is None
    assert rec["would_reject_fakeout"] is False
    assert rec["would_flag_cvd_divergence"] is False
    assert rec["would_force_exit_liquidity_crash"] is False
    print("✓ shadow with absent data -> all verdicts False (never blocks)")


def main() -> int:
    test_collector_parses_depth_and_grows_history()
    test_collector_failure_degrades_safely()
    test_collector_tape_from_df()
    test_shadow_disabled_is_noop()
    test_shadow_records_verdicts_and_logs()
    test_shadow_absent_data_never_blocks()
    print("\n✅ Phase A depth-collector + microstructure-shadow self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
