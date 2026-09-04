"""test_shadow_calibration.py — 校准流水线的合成数据回归。

覆盖：
  1. JSONL 加载容忍损坏行
  2. 覆盖率统计（条数/非空率）
  3. 结果对齐的方向调整（long/short 符号正确）
  4. 样本不足 → insufficient，不外推
  5. 有真信号 → recommended（置换检验通过）
  6. 纯噪声 → no_edge（置换检验拦截）
  7. OBI 全 null → insufficient 且注明订阅缺口
"""
from __future__ import annotations

import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shadow_calibration import (Outcome, coverage, join_outcomes, load_jsonl,
                                obi_analysis, recommend_threshold)

T0 = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)


def _ts_rows(n, symbol="MES"):
    return [{"ts": (T0 + timedelta(minutes=i)).isoformat(), "symbol": symbol,
             "direction": "long" if i % 2 == 0 else "short",
             "prob_dir": 0.5 + (i % 50) / 100.0, "horizon": 5}
            for i in range(n)]


class TestLoadAndCoverage(unittest.TestCase):
    def test_load_tolerates_corrupt_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.log"
            p.write_text('{"a":1}\nNOT_JSON\n{"a":2}\n\n', encoding="utf-8")
            rows = load_jsonl(p)
        self.assertEqual(len(rows), 2)

    def test_coverage_counts_and_nonnull(self):
        rows = _ts_rows(10)
        rows[0]["prob_dir"] = None
        cov = coverage(rows, ["prob_dir"])
        self.assertEqual(cov["MES"]["rows"], 10)
        self.assertAlmostEqual(cov["MES"]["prob_dir_nonnull"], 0.9)


class TestOutcomeJoin(unittest.TestCase):
    def test_direction_sign_and_hit(self):
        rows = [{"ts": T0.isoformat(), "symbol": "MES", "direction": "long",
                 "prob_dir": 0.9, "horizon": 5},
                {"ts": T0.isoformat(), "symbol": "MES", "direction": "short",
                 "prob_dir": 0.9, "horizon": 5}]
        # c0=100, c1=101：多头 hit、空头 miss
        fetcher = lambda sym, ts, h: 100.0 if h == 0 else 101.0
        oc = join_outcomes(rows, fetcher)
        self.assertEqual(len(oc), 2)
        long_o = [o for o in oc if o.direction == "long"][0]
        short_o = [o for o in oc if o.direction == "short"][0]
        self.assertTrue(long_o.hit)
        self.assertFalse(short_o.hit)
        self.assertAlmostEqual(long_o.realized_move, 0.01, places=4)
        self.assertAlmostEqual(short_o.realized_move, -0.01, places=4)

    def test_missing_bars_skipped(self):
        rows = [{"ts": T0.isoformat(), "symbol": "XX", "direction": "long",
                 "prob_dir": 0.9, "horizon": 5}]
        oc = join_outcomes(rows, lambda s, t, h: None)
        self.assertEqual(oc, [])


class TestThresholdRecommendation(unittest.TestCase):
    def _outcomes(self, n, signal: bool, seed=1):
        """signal=True: prob 高 → 必中；False: prob 与结果无关。"""
        rng = random.Random(seed)
        out = []
        for i in range(n):
            p = rng.uniform(0.5, 0.99)
            hit = (p > 0.75) if signal else (rng.random() < 0.5)
            out.append(Outcome(ts=T0, symbol="MES", direction="long",
                               prob_dir=p, realized_move=0.001 if hit else -0.001,
                               hit=hit))
        return out

    def test_insufficient_samples_not_extrapolated(self):
        rec = recommend_threshold(self._outcomes(10, signal=True), "MES",
                                  min_samples=30)
        self.assertEqual(rec.status, "insufficient")
        self.assertIsNone(rec.best_threshold)

    def test_real_signal_recommended(self):
        rec = recommend_threshold(self._outcomes(200, signal=True), "MES",
                                  min_samples=30, permutations=100)
        self.assertEqual(rec.status, "recommended")
        self.assertIsNotNone(rec.best_threshold)
        self.assertGreater(rec.best_hit, rec.perm_p95)

    def test_noise_blocked_by_permutation(self):
        rec = recommend_threshold(self._outcomes(200, signal=False), "MES",
                                  min_samples=30, permutations=100)
        self.assertEqual(rec.status, "no_edge")


class TestObiAnalysis(unittest.TestCase):
    def test_all_null_obi_is_insufficient(self):
        rows = [{"symbol": "EURUSD", "obi": None, "would_reject_fakeout": False}
                for _ in range(50)]
        res = obi_analysis(rows, min_samples=30)
        self.assertEqual(res["EURUSD"]["status"], "insufficient")
        self.assertIn("订阅", res["EURUSD"]["note"])

    def test_measurable_when_enough_obi(self):
        rows = [{"symbol": "EURUSD", "obi": 0.1 + i * 0.01,
                 "would_reject_fakeout": i % 3 == 0} for i in range(40)]
        res = obi_analysis(rows, min_samples=30)
        self.assertEqual(res["EURUSD"]["status"], "measurable")
        self.assertIn("obi_p50", res["EURUSD"])


def main() -> int:
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("✓ shadow calibration (load/join/threshold/permutation/obi) passed")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
