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
from .advanced.macro_regime_engine import RegimeInput, infer_macro_regime
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

    def __init__(self, learning: LearningEngine, max_account_risk: float = 0.02):
        self.learning = learning
        self.max_account_risk = max_account_risk

    def _infer_regime(
        self,
        event: MacroEvent,
        state: MarketState,
        related: Dict[str, MarketState],
    ) -> Tuple[MacroRegime, Dict[str, float], List[str]]:
        related_states = list(related.values())
        equity_state = next((s for s in related_states if s.asset == AssetClass.INDEX), None)
        crypto_state = next((s for s in related_states if s.asset == AssetClass.CRYPTO), None)
        oil_state = next((s for s in related_states if s.asset == AssetClass.OIL), None)
        rates_state = next((s for s in related_states if s.asset == AssetClass.RATES), None)
        fx_state = next((s for s in related_states if s.asset == AssetClass.FX), None)
        vix_proxy = max(
            0.0,
            (1.0 - (equity_state.liquidity_score if equity_state else state.liquidity_score)) * 3.0
            + max(0.0, (equity_state.volatility_z if equity_state else state.volatility_z) - 1.0) * 0.25,
        )
        regime_input = RegimeInput(
            dxy_momentum=(fx_state.momentum_score - 0.5) * 4.0 if fx_state else (state.momentum_score - 0.5) * 2.0,
            us2y_yield_momentum=(rates_state.momentum_score - 0.5) * 4.0 if rates_state else 0.0,
            us10y_yield_momentum=(rates_state.trend_persistence - 0.5) * 4.0 if rates_state else 0.0,
            breakeven_inflation_momentum=event.surprise_score * 0.8 + event.policy_score * 0.3,
            gold_momentum=max(0.0, 0.6 - state.cross_asset_alignment),
            oil_momentum=(oil_state.momentum_score - 0.5) * 4.0 if oil_state else 0.0,
            equity_momentum=(equity_state.momentum_score - 0.5) * 4.0 if equity_state else 0.0,
            vix_momentum=vix_proxy,
            credit_spread_momentum=max(0.0, 0.7 - state.liquidity_score) * 3.0,
            btc_momentum=(crypto_state.momentum_score - 0.5) * 4.0 if crypto_state else 0.0,
            policy_hawkishness=event.policy_score * 2.0 - 1.0,
            geopolitical_tension=event.geopolitical_score * 3.0,
            liquidity_stress=event.liquidity_score * 3.0 + max(0.0, 0.55 - state.liquidity_score) * 2.0,
        )
        regime_output = infer_macro_regime(regime_input)
        regime_map = {
            "risk_on": MacroRegime.RISK_ON,
            "risk_off": MacroRegime.RISK_OFF,
            "inflation_shock": MacroRegime.INFLATION_SHOCK,
            "growth_shock": MacroRegime.MIXED,
            "liquidity_crisis": MacroRegime.LIQUIDITY_STRESS,
            "central_bank_pivot": MacroRegime.MIXED,
            "war_shock": MacroRegime.WAR_SHOCK,
            "dollar_squeeze": MacroRegime.LIQUIDITY_STRESS,
            "neutral": MacroRegime.MIXED,
        }
        translated = regime_map.get(regime_output.primary.value, MacroRegime.MIXED)
        probabilities = {k.value: round(v, 4) for k, v in regime_output.probabilities.items()}
        return translated, probabilities, regime_output.explanation

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
        direction = infer_direction(state)

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
            f"wait_seconds={wait.min_wait_seconds}",
            *posterior.signals_used,
        ]
        invalidation = [
            "news_alignment_below_0.38",
            "cross_asset_alignment_below_0.38",
            "spread_bps_above_30",
            "reversal_score_above_0.68",
            "confidence_decay_above_0.22",
            "profit_giveback_above_35pct_of_mfe",
        ]
        if direction == Direction.FLAT or execution_confidence < 0.70:
            action = DecisionAction.WATCH
            risk = 0.0
            reasons.append("direction_or_confidence_not_confirmed")
        return EventDecision(
            action=action,
            grade=grade,
            asset=state.asset,
            symbol=state.symbol,
            direction=direction,
            raw_score=severity.severity_score,
            calibrated_confidence=posterior.posterior,
            execution_confidence=execution_confidence,
            wait_seconds=wait.min_wait_seconds,
            max_risk_fraction=risk,
            reasons=reasons,
            invalidation_rules=invalidation,
            metadata={
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "action_band": posterior.action_band,
                "wait_reason": wait.reason,
                "severity_tradeable": severity.tradeable,
                "macro_regime": regime.value,
                "macro_regime_probabilities": regime_probs,
                "macro_regime_explanation": regime_explanation,
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
