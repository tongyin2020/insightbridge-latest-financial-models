"""Offline self-check for the microstructure shadow analyzer (descriptive only)."""
from __future__ import annotations

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_microstructure_shadow import load_records, summarize, render

_ROWS = [
    {"stage": "microstructure_shadow", "ts": "2026-07-05T00:00:00+00:00",
     "symbol": "BTC", "obi": 0.40, "would_reject_fakeout": False,
     "would_flag_cvd_divergence": False, "would_force_exit_liquidity_crash": False,
     "n_bid_levels": 5, "n_ask_levels": 5, "tape_source": "bar_1m"},
    {"stage": "microstructure_shadow", "ts": "2026-07-05T00:01:00+00:00",
     "symbol": "BTC", "obi": -0.10, "would_reject_fakeout": True,
     "would_flag_cvd_divergence": True, "would_force_exit_liquidity_crash": False,
     "n_bid_levels": 5, "n_ask_levels": 5, "tape_source": "bar_1m"},
    {"stage": "microstructure_shadow", "ts": "2026-07-05T00:02:00+00:00",
     "symbol": "EURUSD", "obi": None, "would_reject_fakeout": False,
     "would_flag_cvd_divergence": False, "would_force_exit_liquidity_crash": False,
     "n_bid_levels": 0, "n_ask_levels": 0, "tape_source": "bar_1m"},
    {"stage": "other", "ts": "2026-07-05T00:03:00+00:00"},
]


def _write(tmp: Path) -> Path:
    p = tmp / "shadow.log"
    with p.open("w", encoding="utf-8") as fh:
        for r in _ROWS:
            fh.write(json.dumps(r) + "\n")
    return p


def test_loads_only_shadow_stage(tmp_path):
    recs = load_records(_write(tmp_path))
    assert len(recs) == 3  # the "other" stage row is dropped


def test_summary_counts_and_rates(tmp_path):
    s = summarize(load_records(_write(tmp_path)))
    assert s["total_records"] == 3
    btc = s["by_symbol"]["BTC"]
    assert btc["n"] == 2
    assert btc["depth_available_rate"] == 1.0
    assert btc["obi_null_rate"] == 0.0
    assert btc["would_reject_fakeout_rate"] == 0.5
    assert btc["obi_stats"]["min"] == -0.1
    assert btc["obi_stats"]["max"] == 0.4
    eur = s["by_symbol"]["EURUSD"]
    assert eur["obi_null_rate"] == 1.0
    assert eur["obi_stats"] is None


def test_render_empty():
    assert "还没有任何记录" in render(summarize([]))


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tp = Path(d)
        test_loads_only_shadow_stage(tp)
        test_summary_counts_and_rates(tp)
    test_render_empty()
    print("ALL ANALYZER TESTS PASSED")
