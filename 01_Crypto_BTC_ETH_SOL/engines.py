"""
Trading System Engines
Based on user's design specification for BTC/ETH/SOL short-term trading
"""
from models import (
    FeatureSnapshot, SignalCandidate, GateInput, GateDecision,
    Regime, EventState, FragilityState, GateAction, SignalType
)
from typing import Optional


class RegimeEngine:
    """
    Determines market regime per symbol:
    - NORMAL: Standard trading conditions
    - MOMENTUM: Trend/push environment
    - SQUEEZE_RISK: High leverage, concentrated liquidations
    - UNSTABLE: Should not trade
    """
    
    def evaluate(self, snapshot: FeatureSnapshot) -> Regime:
        # Check for unstable conditions first
        if snapshot.stale_quote or snapshot.venue_divergence > 2.0:
            return Regime.UNSTABLE
        
        if snapshot.exchange_incident_flag or snapshot.network_incident_flag:
            return Regime.UNSTABLE
        
        # Check for squeeze risk
        if abs(snapshot.oi_delta_ratio) > 1.8 and snapshot.liquidation_proximity > 0.7:
            return Regime.SQUEEZE_RISK
        
        if abs(snapshot.funding_rate) > 0.001:  # Extreme funding
            return Regime.SQUEEZE_RISK
        
        # Check for momentum
        if max(snapshot.taker_buy_ratio, snapshot.taker_sell_ratio) > 0.6:
            return Regime.MOMENTUM
        
        if abs(snapshot.oi_delta_ratio) > 0.8:
            return Regime.MOMENTUM
        
        return Regime.NORMAL


class EventResponseEngine:
    """
    Manages event-based trading decisions
    Purpose: Don't trade the first shock blindly, wait for structure to mature
    """
    
    def __init__(self, max_wait_seconds: int = 60):
        self.max_wait_seconds = max_wait_seconds
    
    def evaluate(self, snapshot: FeatureSnapshot, elapsed_seconds: float, event_flag: bool) -> EventState:
        if not event_flag:
            return EventState.READY
        
        if elapsed_seconds > self.max_wait_seconds:
            return EventState.INVALID
        
        # Check if market structure is still unstable
        if snapshot.spread_ratio > 1.5 or snapshot.depth_shrink_ratio > 1.5:
            return EventState.WAIT
        
        # Check if direction is confirming
        if snapshot.liquidation_proximity > 0.6 or abs(snapshot.oi_delta_ratio) > 1.2:
            return EventState.READY
        
        return EventState.WAIT


class FragilityEngine:
    """
    Identifies markets that look directional but are too fragile to hold
    """
    
    def evaluate(self, snapshot: FeatureSnapshot) -> FragilityState:
        # HIGH fragility conditions
        if (
            snapshot.stale_quote
            or snapshot.network_incident_flag
            or snapshot.exchange_incident_flag
            or snapshot.spread_ratio > 2.0
            or snapshot.depth_shrink_ratio > 2.0
            or snapshot.venue_divergence > 2.0
            or snapshot.abnormal_wick_score > 0.8
        ):
            return FragilityState.HIGH
        
        # MEDIUM fragility conditions
        if (
            snapshot.spread_ratio > 1.4
            or snapshot.depth_shrink_ratio > 1.4
            or snapshot.venue_divergence > 1.3
            or snapshot.abnormal_wick_score > 0.5
            or abs(snapshot.funding_rate) > 0.0005
        ):
            return FragilityState.MEDIUM
        
        return FragilityState.LOW


class SignalEngine:
    """
    Base signal generation engine
    Computes Direction Score, Conviction Score, and Fragility Score
    """
    
    def __init__(self, symbol: str = "BASE"):
        self.symbol = symbol
    
    def generate(self, snapshot: FeatureSnapshot, regime: Regime, fragility: FragilityState) -> SignalCandidate:
        direction_score = self.direction_score(snapshot)
        conviction_score = self.conviction_score(snapshot)
        fragility_score = self.fragility_score(snapshot)
        
        # Block on high fragility
        if fragility == FragilityState.HIGH:
            return SignalCandidate(
                snapshot.symbol, snapshot.ts, None,
                direction_score, conviction_score, fragility_score,
                SignalType.NO_TRADE.value, ["FRAGILITY_HIGH"]
            )
        
        # Block on unstable regime
        if regime == Regime.UNSTABLE:
            return SignalCandidate(
                snapshot.symbol, snapshot.ts, None,
                direction_score, conviction_score, fragility_score,
                SignalType.NO_TRADE.value, ["REGIME_UNSTABLE"]
            )
        
        # Generate signal based on scores
        if direction_score >= 60 and conviction_score >= 55:
            return SignalCandidate(
                snapshot.symbol, snapshot.ts, "LONG",
                direction_score, conviction_score, fragility_score,
                SignalType.LONG_CANDIDATE.value, ["DIRECTION_LONG", "CONVICTION_OK"]
            )
        
        if direction_score <= 40 and conviction_score >= 55:
            return SignalCandidate(
                snapshot.symbol, snapshot.ts, "SHORT",
                direction_score, conviction_score, fragility_score,
                SignalType.SHORT_CANDIDATE.value, ["DIRECTION_SHORT", "CONVICTION_OK"]
            )
        
        return SignalCandidate(
            snapshot.symbol, snapshot.ts, None,
            direction_score, conviction_score, fragility_score,
            SignalType.NO_TRADE.value, ["INSUFFICIENT_EDGE"]
        )
    
    def direction_score(self, snapshot: FeatureSnapshot) -> float:
        """Calculate direction score (0-100, 50 = neutral)"""
        # Taker imbalance contribution
        taker_component = (snapshot.taker_buy_ratio - snapshot.taker_sell_ratio) * 30.0
        
        # OI delta contribution
        oi_component = snapshot.oi_delta_ratio * 15.0
        
        # Funding rate contribution (negative funding = bullish, positive = bearish)
        funding_component = -snapshot.funding_rate * 10000 * 5.0
        
        score = 50.0 + taker_component + oi_component + funding_component
        return max(0.0, min(100.0, score))
    
    def conviction_score(self, snapshot: FeatureSnapshot) -> float:
        """Calculate conviction score (0-100)"""
        base = 40.0
        
        # OI delta adds conviction
        oi_contribution = abs(snapshot.oi_delta_ratio) * 20.0
        
        # Liquidation proximity adds conviction
        liquidation_contribution = snapshot.liquidation_proximity * 25.0
        
        # Volume imbalance adds conviction
        volume_imbalance = abs(snapshot.taker_buy_ratio - snapshot.taker_sell_ratio)
        volume_contribution = volume_imbalance * 15.0
        
        score = base + oi_contribution + liquidation_contribution + volume_contribution
        return max(0.0, min(100.0, score))
    
    def fragility_score(self, snapshot: FeatureSnapshot) -> float:
        """Calculate fragility score (0-100, higher = more fragile)"""
        spread_contribution = snapshot.spread_ratio * 15.0
        depth_contribution = snapshot.depth_shrink_ratio * 15.0
        venue_contribution = snapshot.venue_divergence * 15.0
        wick_contribution = snapshot.abnormal_wick_score * 20.0
        stale_contribution = 25.0 if snapshot.stale_quote else 0.0
        
        score = spread_contribution + depth_contribution + venue_contribution + wick_contribution + stale_contribution
        return max(0.0, min(100.0, score))


class BTCSignalEngine(SignalEngine):
    """BTC-specific signal engine with derivatives-led, macro-filtered approach"""
    
    def __init__(self):
        super().__init__("BTC")
    
    def direction_score(self, snapshot: FeatureSnapshot) -> float:
        base_score = super().direction_score(snapshot)
        # BTC weights derivatives factors more heavily
        oi_bonus = snapshot.oi_delta_ratio * 10.0
        return max(0.0, min(100.0, base_score + oi_bonus))


class ETHSignalEngine(SignalEngine):
    """ETH-specific signal engine - balanced hybrid approach"""
    
    def __init__(self):
        super().__init__("ETH")


class SOLSignalEngine(SignalEngine):
    """SOL-specific signal engine - high-beta, liquidity-sensitive"""
    
    def __init__(self):
        super().__init__("SOL")
    
    def fragility_score(self, snapshot: FeatureSnapshot) -> float:
        # SOL is more sensitive to liquidity issues
        base_score = super().fragility_score(snapshot)
        liquidity_penalty = snapshot.spread_ratio * 10.0
        return max(0.0, min(100.0, base_score + liquidity_penalty))


class ExecutionGate:
    """
    The Execution Gate - final decision maker
    Priority:
    1. System/data safety
    2. Deterioration / UNSTABLE regime
    3. Cooldown / recovery
    4. Event readiness
    5. Signal quality
    """
    
    def decide(self, gi: GateInput) -> GateDecision:
        # Priority 1: System/data safety
        if gi.exchange_incident_flag or gi.network_incident_flag:
            return GateDecision(GateAction.FREEZE, None, 0.0, ["INCIDENT_FLAG"])
        
        if gi.stale_quote:
            return GateDecision(GateAction.BLOCK, None, 0.0, ["STALE_QUOTE"])
        
        if gi.venue_divergence > 2.0:
            return GateDecision(GateAction.BLOCK, None, 0.0, ["VENUE_DIVERGENCE"])
        
        # Priority 2: Deterioration / UNSTABLE regime
        if gi.regime == Regime.UNSTABLE or gi.deterioration_triggered or gi.fragility == FragilityState.HIGH:
            if gi.position_open:
                return GateDecision(GateAction.EXIT_NOW, gi.position_side, 0.0, ["DETERIORATION_EXIT"])
            return GateDecision(GateAction.FREEZE, None, 0.0, ["MARKET_UNSTABLE"])
        
        # Priority 3: Cooldown / recovery
        if gi.cooldown_state == "COOLDOWN":
            return GateDecision(GateAction.BLOCK, None, 0.0, ["COOLDOWN_ACTIVE"])
        
        if gi.daily_drawdown_hit:
            return GateDecision(GateAction.FREEZE, None, 0.0, ["DAILY_DD_LIMIT"])
        
        # Time stop check
        if gi.position_open and gi.position_age_minutes >= gi.max_position_age_minutes:
            return GateDecision(GateAction.EXIT_NOW, gi.position_side, 0.0, ["TIME_STOP"])
        
        # Priority 4: Event readiness
        if gi.event_state in (EventState.WAIT, EventState.INVALID):
            return GateDecision(GateAction.BLOCK, None, 0.0, [f"EVENT_{gi.event_state.value}"])
        
        # Priority 5: Signal quality
        if not gi.trade_allowed or not gi.signal_side:
            return GateDecision(GateAction.BLOCK, None, 0.0, ["NO_VALID_SIGNAL"])
        
        # Reduced mode for medium fragility
        if gi.fragility == FragilityState.MEDIUM or gi.risk_multiplier < 1.0:
            return GateDecision(
                GateAction.ALLOW_REDUCED, gi.signal_side,
                max(0.1, gi.risk_multiplier), ["REDUCED_MODE"]
            )
        
        return GateDecision(GateAction.ALLOW, gi.signal_side, 1.0, ["ALL_CHECKS_PASS"])


class RiskEngine:
    """
    Risk evaluation for open positions
    Implements layered exit strategy
    """
    
    def evaluate_open_position(
        self,
        unrealized_pnl: float,
        warning: float = -0.02,
        reduce: float = -0.03,
        stop: float = -0.05,
        catastrophe: float = -0.10
    ) -> str:
        if unrealized_pnl <= catastrophe:
            return "CATASTROPHE_EXIT"
        if unrealized_pnl <= stop:
            return "MAIN_STOP"
        if unrealized_pnl <= reduce:
            return "REDUCE_POSITION"
        if unrealized_pnl <= warning:
            return "PRE_WARNING"
        return "HOLD"


# Engine instances
regime_engine = RegimeEngine()
event_response_engine = EventResponseEngine()
fragility_engine = FragilityEngine()
btc_signal_engine = BTCSignalEngine()
eth_signal_engine = ETHSignalEngine()
sol_signal_engine = SOLSignalEngine()
execution_gate = ExecutionGate()
risk_engine = RiskEngine()


def get_signal_engine(symbol: str) -> SignalEngine:
    """Get the appropriate signal engine for a symbol"""
    engines = {
        "BTC": btc_signal_engine,
        "ETH": eth_signal_engine,
        "SOL": sol_signal_engine
    }
    return engines.get(symbol.upper(), SignalEngine(symbol))
