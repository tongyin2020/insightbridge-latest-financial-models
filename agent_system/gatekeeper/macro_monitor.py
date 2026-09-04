from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_system.config import AgentConfig
from agent_system.state import GatekeeperResult
from agent_system.utils import recent_jsonl


class MacroMonitor:
    """第一层：低能耗宏观监控。只读本地日志，无 LLM 调用。"""

    def __init__(self, config: AgentConfig) -> None:
        self.cfg = config

    def _news_score(self, records: list[dict[str, Any]]) -> float:
        if not records:
            return 0.0
        wake_sum = 0.0
        alert_hits = 0
        keyword_pattern = re.compile(
            r"|".join(re.escape(k) for k in self.cfg.macro_alert_keywords), re.IGNORECASE
        )
        for r in records:
            if r.get("would_wake") and r.get("is_relevant"):
                wake_sum += float(r.get("confidence", 0.0))
            text = f"{r.get('text', '')} {r.get('reason', '')}"
            if keyword_pattern.search(text):
                alert_hits += 1
        wake_score = min(wake_sum / 1.5, 1.0)
        alert_score = min(alert_hits / 3.0, 1.0)
        return 0.6 * wake_score + 0.4 * alert_score

    def _volatility_score(self, records: list[dict[str, Any]]) -> float:
        if not records:
            return 0.0
        values: list[float] = []
        for r in records:
            symbol = r.get("symbol", "")
            move = r.get("expected_move_frac")
            if move is None:
                continue
            typical = self.cfg.typical_move_frac.get(symbol, 0.01)
            if typical <= 0:
                typical = 0.01
            values.append(min(abs(float(move)) / typical, 2.0))
        if not values:
            return 0.0
        values.sort()
        tail = values[int(len(values) * 0.9)]
        return min(tail / 2.0, 1.0)

    def _microstructure_score(self, records: list[dict[str, Any]]) -> float:
        if not records:
            return 0.0
        flags = 0
        for r in records:
            if r.get("would_reject_fakeout"):
                flags += 1
            if r.get("would_flag_cvd_divergence"):
                flags += 1
            if r.get("would_force_exit_liquidity_crash"):
                flags += 2
        return min(flags / 2.0, 1.0)

    def _pipeline_health_score(self, records: list[dict[str, Any]]) -> float:
        if not records:
            return 0.0
        halts = sum(1 for r in records if r.get("stage") == "HALT")
        return min(halts / 3.0, 1.0)

    def evaluate(self) -> GatekeeperResult:
        lookback = self.cfg.log_window_minutes
        news_records = recent_jsonl(
            self.cfg.base_dir / "reports" / "runtime" / "news_shadow.log",
            self.cfg.news_lookback_minutes,
        )
        ts_records = recent_jsonl(
            self.cfg.base_dir / "reports" / "runtime" / "timeseries_shadow.log",
            lookback,
        )
        ms_records = recent_jsonl(
            self.cfg.base_dir / "reports" / "runtime" / "microstructure_shadow.log",
            lookback,
        )
        pipeline_records = recent_jsonl(
            self.cfg.base_dir / "reports" / "runtime" / "continuous.log",
            lookback,
        )

        factors = {
            "news": self._news_score(news_records),
            "volatility": self._volatility_score(ts_records),
            "microstructure": self._microstructure_score(ms_records),
            "pipeline_health": self._pipeline_health_score(pipeline_records),
        }
        weights = self.cfg.gatekeeper_weights
        score = sum(factors[k] * weights.get(k, 0.0) for k in factors)
        phase = "CRISIS_AWAKEN" if score >= self.cfg.crisis_threshold else "MONITOR"

        if phase == "CRISIS_AWAKEN":
            top = max(factors, key=factors.get)
            reason = (
                f"宏观异动分数 {score:.3f} 超过阈值 {self.cfg.crisis_threshold:.3f}；"
                f"主要因子: {top}={factors[top]:.3f}"
            )
        else:
            top = max(factors, key=factors.get) if factors else "none"
            reason = (
                f"市场平稳：最高因子 {top}={factors.get(top, 0.0):.3f}，"
                f"综合分数 {score:.3f} 低于危机阈值 {self.cfg.crisis_threshold:.3f}"
            )

        return GatekeeperResult(
            ts=datetime.now(timezone.utc),
            phase=phase,
            score=score,
            threshold=self.cfg.crisis_threshold,
            factors=factors,
            reason=reason,
        )
