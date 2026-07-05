"""Offline self-check for the standalone microstructure recorder.

No TWS needed: a fake ``ib`` duck-types ``reqHistoricalData`` / ``reqMktDepth`` /
``sleep`` / ``cancelMktDepth`` and a fake resolver returns a locked contract.
Verifies ``record_once`` writes observe-only JSONL and never raises.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from depth_collector import DepthCollector
from microstructure_shadow import MicrostructureShadow
from record_microstructure import record_once


class _Bar:
    def __init__(self, c, v):
        self.open = c
        self.high = c
        self.low = c
        self.close = c
        self.volume = v


class _DomLvl:
    def __init__(self, size):
        self.size = size


class _DepthTkr:
    def __init__(self, bids, asks):
        self.domBids = [_DomLvl(s) for s in bids]
        self.domAsks = [_DomLvl(s) for s in asks]


class _FakeIB:
    def __init__(self, bids, asks, raise_depth=False):
        self._bids = bids
        self._asks = asks
        self._raise_depth = raise_depth

    def reqHistoricalData(self, *a, **k):
        return [_Bar(100 + i * 0.1, 10 + i) for i in range(60)]

    def reqMktDepth(self, contract, numRows=5):
        if self._raise_depth:
            raise RuntimeError("no depth permission")
        return _DepthTkr(self._bids, self._asks)

    def sleep(self, s):
        return None

    def cancelMktDepth(self, contract):
        return None


class _RC:
    def __init__(self, symbol):
        self.symbol = symbol
        self.sec_type = "CASH"
        self.con_id = 123
        self.raw = object()

    @property
    def is_locked(self):
        return self.con_id > 0


class _FakeResolver:
    def get_cached(self, sym):
        return None

    def resolve(self, sym, refresh=False):
        return _RC(sym)


def _run(fake_ib, tmp_log):
    shadow = MicrostructureShadow(enabled=True, log_path=str(tmp_log))
    if not shadow.ms_ok:
        print("SKIP: Step-1 primitives unavailable")
        return None
    collector = DepthCollector(depth_sleep=0.0)
    resolver = _FakeResolver()
    written = record_once(fake_ib, resolver, collector, shadow, ["EURUSD", "USDJPY"])
    return written


def test_records_verdicts_and_writes_jsonl(tmp_path=None):
    tmp_log = Path(tmp_path or ".") / "rec_test.log"
    if tmp_log.exists():
        tmp_log.unlink()
    written = _run(_FakeIB([5, 4, 3, 2, 1], [1, 1, 1, 1, 1]), tmp_log)
    if written is None:
        return
    assert written == 2, written
    lines = tmp_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, lines
    rec = json.loads(lines[0])
    assert rec["stage"] == "microstructure_shadow"
    assert rec["symbol"] == "EURUSD"
    assert rec["obi"] is not None
    assert rec["n_bid_levels"] == 5
    assert rec["tape_source"] == "bar_1m"
    tmp_log.unlink()
    print("ok: records verdicts and writes jsonl")


def test_depth_failure_degrades_and_never_raises(tmp_path=None):
    tmp_log = Path(tmp_path or ".") / "rec_test2.log"
    if tmp_log.exists():
        tmp_log.unlink()
    written = _run(_FakeIB([], [], raise_depth=True), tmp_log)
    if written is None:
        return
    # Still writes a line per symbol (obi None), never raises.
    assert written == 2, written
    rec = json.loads(tmp_log.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["obi"] is None
    assert rec["would_reject_fakeout"] is False
    tmp_log.unlink()
    print("ok: depth failure degrades safely")


def test_disabled_shadow_writes_nothing(tmp_path=None):
    tmp_log = Path(tmp_path or ".") / "rec_test3.log"
    if tmp_log.exists():
        tmp_log.unlink()
    shadow = MicrostructureShadow(enabled=False, log_path=str(tmp_log))
    collector = DepthCollector(depth_sleep=0.0)
    written = record_once(_FakeIB([5, 4], [1, 1]), _FakeResolver(), collector,
                          shadow, ["EURUSD"])
    assert written == 0, written
    assert not tmp_log.exists()
    print("ok: disabled shadow writes nothing")


if __name__ == "__main__":
    os.environ.pop("EVENTALPHA_MICROSTRUCTURE_SHADOW", None)
    test_records_verdicts_and_writes_jsonl()
    test_depth_failure_degrades_and_never_raises()
    test_disabled_shadow_writes_nothing()
    print("ALL RECORDER TESTS PASSED")
