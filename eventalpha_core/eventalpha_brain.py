from __future__ import annotations

from typing import Dict, List, Tuple

from .cross_asset import cross_asset_score, infer_direction
from .learning_engine import LearningEngine
from .position_sizing import risk_fraction
from .schema import AssetClass, DecisionAction, Direction, EventDecision, EventGrade, ExitDecision, MacroEvent, MacroRegime, MarketState, PositionState
from .advanced.asset_ranking_engine import AssetRank, rank_assets
from .advanced.bayesian_confidence_engine import combine_signals, default_event_signals
from .advanced.escape_engine import escape_decision
from .advanced.event_severity_engine import event_severity
from .advanced.measured_timing import impact_bucket, measured_wait_window_by_impact
from .advanced.waiting_policy_engine import waiting_policy


def _clip01(x: float) -> float:
    return max(0.01, min(0.99, x))


class EventAlphaBrain:
    """Unified decision brain above all five trading bots.

    Version 2.1 integrates:
    - event severity scoring
    - Bayesian confidence fusion
    - adaptive waiting policy
    - cross-asset ranking
    """

    def __init__(
        self,
        learning: LearningEngine,
        max_account_risk: float = 0.02,
        selectivity_enabled: bool = False,
        microstructure_exit_enabled: bool = False,
    ):
        self.learning = learning
        self.max_account_risk = max_account_risk
        # Selectivity gate: the only logic change the P&L study proved adds edge --
        # stand down on small-impact events and use the impact-scaled window on
        # decisive ones. Default OFF so the decision chain is byte-for-byte
        # unchanged unless a caller opts in (paper first). See advanced.measured_timing.
        self.selectivity_enabled = selectivity_enabled
        # Capital-safety microstructure exits (CVD divergence, near-side liquidity
        # crash, hard hold cap). Default OFF -> exit path unchanged. Thresholds are
        # UNVALIDATED placeholders to be calibrated on real data (Step 2).
        self.microstructure_exit_enabled = microstructure_exit_enabled

    @staticmethod
    def _early_move_bps(state: MarketState) -> float | None:
        if state.early_move_bps is not None:
            return state.early_move_bps
        raw = state.raw or {}
        v = raw.get("early_move_bps")
        return float(v) if v is not None else None

    def _infer_regime(
        self,
        event: MacroEvent,
        state: MarketState,
        related: Dict[str, MarketState],
    ) -> Tuple[MacroRegime, Dict[str, float], List[str]]:
        # 宏观因子已按 2024-2025 真实数据验证为无交易优势（新闻情绪≈掷硬币、
        # 宏观 surprise 在 30-60s 内被价格消化），故移除宏观 regime 推断，固定返回中性。
        return MacroRegime.MIXED, {}, ["macro_factor_retired"]

    def rank_assets_for_event(
        self,
        event: MacroEvent,
        states: Dict[AssetClass, MarketState],
    ) -> List[AssetRank]:
        memory_edges = {
            asset: self.learning.memory_edge(event.event_type, asset)
            for asset in states
        }
        return rank_assets(event, states, memory_edges=memory_edges)

    def decide(self, event: MacroEvent, state: MarketState, related: Dict[str, MarketState] | None = None) -> EventDecision:
        related = related or {}
        regime, regime_probs, regime_explanation = self._infer_regime(event, state, related)
        severity = event_severity(
            event,
            forecast_surprise=abs(event.surprise_score),
            market_gap_score=min(state.volatility_z / 3.0, 1.0),
        )
        grade = severity.grade
        if grade == EventGrade.IGNORE:
            return EventDecision(
                action=DecisionAction.IGNORE,
                grade=grade,
                asset=state.asset,
                symbol=state.symbol,
                direction=Direction.FLAT,
                raw_score=0.0,
                calibrated_confidence=0.0,
                execution_confidence=0.0,
                wait_seconds=0,
                max_risk_fraction=0.0,
                reasons=["event_not_material_enough", *severity.reasons],
                invalidation_rules=[],
            )

        state.cross_asset_alignment = cross_asset_score(state, related)
        memory_edge = self.learning.memory_edge(event.event_type, state.asset)
        memory_wait = self.learning.memory_wait(event.event_type, state.asset)

        macro_direction = _clip01(
            0.50
            + (state.momentum_score - 0.50) * 0.50
            + event.narrative_bias * 0.20
        )
        if regime in (MacroRegime.INFLATION_SHOCK, MacroRegime.WAR_SHOCK):
            macro_direction = _clip01(macro_direction + 0.05)
        if regime == MacroRegime.LIQUIDITY_STRESS:
            macro_direction = _clip01(macro_direction - 0.06)
        price_confirmation = _clip01(
            0.35 * state.momentum_score
            + 0.25 * state.orderbook_pressure
            + 0.25 * state.trend_persistence
            + 0.15 * (1.0 - state.reversal_score)
        )
        liquidity_quality = _clip01(
            0.75 * state.liquidity_score
            + 0.25 * state.execution_quality
            - min(state.spread_bps / 100.0, 0.20)
        )

        posterior = combine_signals(
            prior=max(0.20, severity.severity_score),
            signals=default_event_signals(
                macro_direction=macro_direction,
                news=state.news_alignment,
                price_confirmation=price_confirmation,
                cross_asset=state.cross_asset_alignment,
                liquidity=liquidity_quality,
                memory=memory_edge,
            ),
        )
        wait = waiting_policy(
            event,
            state,
            severity_score=severity.severity_score,
            memory_best_wait=memory_wait,
        )
        wait_seconds = wait.min_wait_seconds
        max_wait_seconds = wait.max_wait_seconds
        direction = infer_direction(state)

        # --- selectivity gate (opt-in) ---------------------------------------
        # Pick the impact bucket from the market's own early-move magnitude and,
        # when enabled: stand down on 'small' events, and adopt the measured
        # impact-scaled window (faster entry, longer hold) on 'mid'/'big' ones.
        early_move_bps = self._early_move_bps(state)
        bucket = impact_bucket(state.asset, early_move_bps) if early_move_bps is not None else None
        impact_window = (
            measured_wait_window_by_impact(state.asset, early_move_bps)
            if early_move_bps is not None
            else None
        )
        selectivity_stand_down = False
        selectivity_applied = False
        if self.selectivity_enabled and bucket is not None:
            if bucket == "small":
                selectivity_stand_down = True
                selectivity_applied = True
            elif impact_window is not None:
                wait_seconds, max_wait_seconds, _time_stop = impact_window
                selectivity_applied = True

        execution_confidence = _clip01(
            posterior.posterior
            - (0.08 if state.spread_bps > 30 else 0.0)
            - (0.05 if state.volatility_z > 4.0 else 0.0)
            - (0.08 if state.reversal_score > 0.58 else 0.0)
            - (0.08 if state.execution_quality < 0.45 else 0.0)
            + (0.04 if regime in (MacroRegime.RISK_ON, MacroRegime.INFLATION_SHOCK) else 0.0)
            - (0.06 if regime == MacroRegime.LIQUIDITY_STRESS else 0.0)
        )
        action, risk = risk_fraction(execution_confidence, grade, self.max_account_risk)
        reasons: List[str] = [
            f"regime={regime.value}",
            f"severity={severity.severity_score:.2f}",
            f"grade={grade.value}",
            f"posterior={posterior.posterior:.2f}",
            f"execution_confidence={execution_confidence:.2f}",
            f"memory_edge={memory_edge:.2f}",
            f"cross_asset_alignment={state.cross_asset_alignment:.2f}",
            f"wait_seconds={wait_seconds}",
            *posterior.signals_used,
        ]
        if bucket is not None:
            reasons.append(f"impact_bucket={bucket}")
        invalidation = [
            "news_alignment_below_0.38",
            "cross_asset_alignment_below_0.38",
            "spread_bps_above_30",
            "reversal_score_above_0.68",
            "confidence_decay_above_0.22",
            "profit_giveback_above_35pct_of_mfe",
        ]
        if direction == Direction.FLAT or execution_confidence < 0.85:
            action = DecisionAction.WATCH
            risk = 0.0
            reasons.append("direction_or_confidence_not_confirmed")
        if selectivity_stand_down:
            action = DecisionAction.WATCH
            risk = 0.0
            reasons.append("selectivity_stand_down_small_impact")
        return EventDecision(
            action=action,
            grade=grade,
            asset=state.asset,
            symbol=state.symbol,
            direction=direction,
            raw_score=severity.severity_score,
            calibrated_confidence=posterior.posterior,
            execution_confidence=execution_confidence,
            wait_seconds=wait_seconds,
            max_risk_fraction=risk,
            reasons=reasons,
            invalidation_rules=invalidation,
            metadata={
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "action_band": posterior.action_band,
                "wait_reason": wait.reason,
                "max_wait_seconds": max_wait_seconds,
                "severity_tradeable": severity.tradeable,
                "macro_regime": regime.value,
                "macro_regime_probabilities": regime_probs,
                "macro_regime_explanation": regime_explanation,
                "early_move_bps": early_move_bps,
                "impact_bucket": bucket,
                "impact_scaled_window": impact_window,
                "selectivity_enabled": self.selectivity_enabled,
                "selectivity_applied": selectivity_applied,
            },
        )

    def assess_exit(
        self,
        position: PositionState,
        mfe_r_multiple: float = 0.0,
        current_r_multiple: float = 0.0,
    ) -> ExitDecision:
        signal = escape_decision(
            position,
            mfe_r_multiple=mfe_r_multiple,
            current_r_multiple=current_r_multiple,
            microstructure_exit_enabled=self.microstructure_exit_enabled,
        )
        reason = "; ".join(signal.reasons) if signal.reasons else "exit_conditions_not_met"
        return ExitDecision(
            action=signal.action,
            urgency=signal.urgency,
            reason=reason,
            reduce_fraction=signal.reduce_fraction,
            metadata={
                "escape_score": signal.score,
                "escape_reasons": signal.reasons,
            },
        )
