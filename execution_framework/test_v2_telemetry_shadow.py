"""Deterministic, data-free self-checks for the observe-only V2TelemetryShadow.
No IB gateway / ib_insync required."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from v2_telemetry_shadow import V2TelemetryShadow


def _check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        raise AssertionError(name)


def test_disabled_is_noop():
    sh = V2TelemetryShadow(enabled=False)
    rec = sh.observe("BTC", connected=True, bid=100.0, ask=100.1,
                     bid_size=10, ask_size=10, latency_s=0.08,
                     tick_epoch=1000.0, now_epoch=1000.2)
    _check("disabled returns None", rec is None)
    _check("disabled observes nothing", sh.n_observed == 0)


def test_enabled_records_healthy():
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "shadow.log"
        sh = V2TelemetryShadow(enabled=True, log_path=str(log))
        _check("v2 package importable", sh.v2_ok)
        _check("enabled active", sh.enabled)
        rec = sh.observe("AUDUSD", connected=True, bid=0.6500, ask=0.65002,
                         bid_size=1_000_000, ask_size=1_000_000,
                         latency_s=0.08, tick_epoch=1000.0, now_epoch=1000.2)
        _check("returns a record", rec is not None)
        _check("quote age computed", abs(rec["quote_age_s"] - 0.2) < 1e-6)
        _check("spread bps present", rec["spread_bps"] is not None)
        _check("gate allowed on healthy quote", rec["exec_gate_allowed"])
        lines = log.read_text().strip().splitlines()
        _check("one jsonl line written", len(lines) == 1)
        _check("jsonl parses", json.loads(lines[0])["symbol"] == "AUDUSD")


def test_enabled_flags_bad_conditions():
    sh = SH = V2TelemetryShadow(enabled=True)
    # disconnected -> gate blocks
    r1 = sh.observe("BTC", connected=False, bid=100.0, ask=100.1,
                    tick_epoch=1000.0, now_epoch=1000.1)
    _check("disconnected blocked", r1 is not None and not r1["exec_gate_allowed"])
    # stale quote -> gate blocks
    r2 = SH.observe("BTC", connected=True, bid=100.0, ask=100.1,
                    tick_epoch=1000.0, now_epoch=1010.0)
    _check("stale quote blocked", not r2["exec_gate_allowed"])
    # crossed book -> spread None (declined upstream), gate still runs
    r3 = SH.observe("BTC", connected=True, bid=100.2, ask=100.0,
                    tick_epoch=1000.0, now_epoch=1000.1)
    _check("crossed book -> spread None", r3["spread_bps"] is None)


def test_reject_rate_feeds_through():
    sh = V2TelemetryShadow(enabled=True)
    for _ in range(10):
        sh.record_order_status("Rejected")
    r = sh.observe("BTC", connected=True, bid=100.0, ask=100.1,
                   tick_epoch=1000.0, now_epoch=1000.1)
    _check("reject rate reflected", r["recent_reject_rate"] > 0.5)
    _check("high reject rate blocks gate", not r["exec_gate_allowed"])


def main():
    for fn in [test_disabled_is_noop, test_enabled_records_healthy,
               test_enabled_flags_bad_conditions, test_reject_rate_feeds_through]:
        print(fn.__name__)
        fn()
    print("\nALL V2 TELEMETRY SHADOW SELF-CHECKS PASSED")


if __name__ == "__main__":
    main()
