from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_system.config import AgentConfig
from agent_system.state import BotSnapshot


@dataclass
class InterlockResult:
    score: float
    threshold: float
    regime_type: str
    primary_bot: str
    primary_direction: str
    secondary_bots: list[str]
    secondary_scale: float
    factors: dict[str, float]


class CrossAssetInterlock:
    """跨资产联动锁：把 5 个机器人的快照合成为单一的宏观制度置信度。"""

    def __init__(self, config: AgentConfig) -> None:
        self.cfg = config

    @staticmethod
    def _dominant_direction(snapshot: BotSnapshot) -> str:
        # Prefer shadow-derived directional bias from expected_move_frac
        ts = snapshot.shadow_summary.get("timeseries_relevant", 0)
        avg_move = snapshot.shadow_summary.get("timeseries_avg_expected_move_frac", 0.0)
        if ts and avg_move:
            return "BUY" if avg_move > 0 else "SELL"
        # fallback to recent trade direction
        if snapshot.latest_trade:
            return snapshot.latest_trade.get("direction", "HOLD")
        return "HOLD"

    def evaluate(self, snapshots: dict[str, BotSnapshot]) -> InterlockResult:
        if not snapshots:
            return InterlockResult(
                score=0.0,
                threshold=0.8,
                regime_type="NONE",
                primary_bot="none",
                primary_direction="HOLD",
                secondary_bots=[],
                secondary_scale=1.0,
                factors={},
            )

        directions = {bid: self._dominant_direction(s) for bid, s in snapshots.items()}
        active = {k: v for k, v in directions.items() if v in ("BUY", "SELL")}

        # Primary bot = highest magnitude of expected move
        scores: dict[str, float] = {}
        for bid, snap in snapshots.items():
            mag = abs(snap.shadow_summary.get("timeseries_avg_expected_move_frac", 0.0))
            wakes = snap.shadow_summary.get("news_would_wake", 0)
            confirms = snap.shadow_summary.get("timeseries_confirm", 0)
            scores[bid] = mag + 0.01 * wakes + 0.005 * confirms

        primary = max(scores, key=scores.get) if scores else list(snapshots.keys())[0]
        primary_dir = active.get(primary, "HOLD")

        # Alignment score: fraction of active bots agreeing with primary
        if active:
            aligned = sum(1 for b, d in active.items() if d == primary_dir and b != primary)
            alignment_score = aligned / len(active)
        else:
            alignment_score = 0.0

        # Magnitude score: average |expected_move| normalized against typical
        mags: list[float] = []
        for bid, snap in snapshots.items():
            for sym in snap.symbols:
                typical = self.cfg.typical_move_frac.get(sym, 0.01)
                if typical <= 0:
                    typical = 0.01
                move = snap.shadow_summary.get("timeseries_avg_expected_move_frac", 0.0)
                mags.append(min(abs(move) / typical, 2.0))
        magnitude_score = sum(mags) / len(mags) if mags else 0.0

        # Macro wake score
        total_wakes = sum(s.shadow_summary.get("news_would_wake", 0) for s in snapshots.values())
        wake_score = min(total_wakes / 5.0, 1.0)

        # Warning score (microstructure red flags reduce interlock)
        warnings = sum(
            s.shadow_summary.get("microstructure_fakeout", 0)
            + s.shadow_summary.get("microstructure_cvd_divergence", 0)
            + s.shadow_summary.get("microstructure_liquidity_crash", 0)
            for s in snapshots.values()
        )
        warning_penalty = min(warnings / 10.0, 0.3)

        composite = (0.4 * alignment_score + 0.35 * magnitude_score + 0.25 * wake_score) - warning_penalty
        composite = max(0.0, min(1.0, composite))

        # Regime type classification
        regime = "GENERIC"
        if primary in ("fx",) and primary_dir in ("BUY", "SELL"):
            regime = "FX_INTERVENTION"
        elif primary in ("oil",) and primary_dir in ("BUY", "SELL"):
            regime = "OIL_GEOPOL"
        elif primary in ("crypto", "index", "bond"):
            regime = primary.upper()

        secondary = [b for b in snapshots if b != primary and b in active]

        return InterlockResult(
            score=round(composite, 4),
            threshold=0.8,
            regime_type=regime,
            primary_bot=primary,
            primary_direction=primary_dir,
            secondary_bots=secondary,
            secondary_scale=0.25,
            factors={
                "alignment": round(alignment_score, 4),
                "magnitude": round(magnitude_score, 4),
                "wake": round(wake_score, 4),
                "warning_penalty": round(warning_penalty, 4),
            },
        )
