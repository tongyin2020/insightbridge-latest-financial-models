"""
WTI Trading Platform - Automated Trading Bot
Human-in-the-Loop: Scans market → Generates opportunities (≥65% confidence) → 
Notifies user → Waits for manual approval → Executes trade
"""
import logging
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OpportunityStatus(str, Enum):
    PENDING = "pending"       # Waiting for user approval
    APPROVED = "approved"     # User approved, executing
    EXECUTED = "executed"     # Trade executed
    REJECTED = "rejected"    # User rejected
    EXPIRED = "expired"      # Not acted on in time
    CANCELLED = "cancelled"  # Bot cancelled (conditions changed)


class TradeDirection(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class TradeOpportunity:
    id: str
    symbol: str
    direction: TradeDirection
    confidence: float           # 0-100
    entry_price: float
    stop_loss: float
    take_profit_1: float        # First target
    take_profit_2: float        # Second target
    size: int                   # Contracts
    reasoning: str
    signal_components: Dict = field(default_factory=dict)
    gate_status: str = ""
    fragility_score: float = 0.0
    regime: str = ""
    status: OpportunityStatus = OpportunityStatus.PENDING
    created_at: str = ""
    expires_at: str = ""
    acted_at: str = ""
    position_id: str = ""       # Set after execution
    exit_tiers: List[Dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.expires_at:
            self.expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 1),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "size": self.size,
            "reasoning": self.reasoning,
            "signal_components": self.signal_components,
            "gate_status": self.gate_status,
            "fragility_score": round(self.fragility_score, 1),
            "regime": self.regime,
            "status": self.status.value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "acted_at": self.acted_at,
            "position_id": self.position_id,
            "exit_tiers": self.exit_tiers,
        }


class TradingBot:
    """
    Automated trading bot with human-in-the-loop confirmation.
    Scans market conditions and generates trade opportunities.
    """

    def __init__(self):
        self.enabled = False
        self.min_confidence = 65.0       # Minimum confidence threshold
        self.scan_interval_sec = 10      # How often to scan
        self.opportunity_ttl_min = 5     # Opportunity expires after 5 min
        self.max_pending = 3             # Max pending opportunities at once
        self.max_daily_trades = 10       # Max trades per day

        self._opportunities: Dict[str, TradeOpportunity] = {}
        self._history: List[TradeOpportunity] = []
        self._daily_trade_count = 0
        self._last_scan_time = None
        self._scan_task = None
        self._notification_callback = None
        self._last_daily_reset = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Track recent signals to avoid duplicate opportunities
        self._recent_signals: Dict[str, datetime] = {}
        self._signal_cooldown_sec = 120  # 2 min cooldown between same-direction signals

    def set_notification_callback(self, callback):
        """Set async callback for sending notifications"""
        self._notification_callback = callback

    def toggle(self, enabled: Optional[bool] = None) -> bool:
        """Toggle bot on/off"""
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = not self.enabled
        logger.info(f"[Bot] {'Enabled' if self.enabled else 'Disabled'}")
        return self.enabled

    def update_config(self, config: Dict):
        """Update bot configuration"""
        if "min_confidence" in config:
            self.min_confidence = max(50, min(95, config["min_confidence"]))
        if "scan_interval_sec" in config:
            self.scan_interval_sec = max(5, min(60, config["scan_interval_sec"]))
        if "max_daily_trades" in config:
            self.max_daily_trades = max(1, min(50, config["max_daily_trades"]))
        if "opportunity_ttl_min" in config:
            self.opportunity_ttl_min = max(1, min(30, config["opportunity_ttl_min"]))

    async def scan_market(
        self,
        symbol: str,
        current_price: float,
        signal_score: Dict,
        execution_gate: Dict,
        fragility: Dict,
        risk_control: Dict,
        regime: str,
        atr: float,
        indicators: Dict,
    ) -> Optional[TradeOpportunity]:
        """
        Core scanning logic. Evaluates market conditions and generates opportunity if criteria met.
        """
        if not self.enabled:
            return None

        self._last_scan_time = datetime.now(timezone.utc).isoformat()

        # Reset daily counter
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_daily_reset:
            self._daily_trade_count = 0
            self._last_daily_reset = today

        # Check daily limit
        if self._daily_trade_count >= self.max_daily_trades:
            return None

        # Check max pending
        pending_count = sum(1 for o in self._opportunities.values() if o.status == OpportunityStatus.PENDING)
        if pending_count >= self.max_pending:
            return None

        # Expire old opportunities
        self._expire_old_opportunities()

        # Check risk control allows trading
        if not risk_control.get("can_trade", True):
            return None

        # Check fragility
        frag_score = fragility.get("score", 0)
        if frag_score >= 80:  # Extreme fragility
            return None

        # Calculate composite confidence
        abs_signal = abs(signal_score.get("score", 0))
        signal_confidence = min(100, abs_signal * 1.2)  # Scale signal to confidence

        # Gate bonus/penalty
        gate_status = execution_gate.get("gate_status", "CLOSED")
        gate_bonus = {"OPEN": 15, "CAUTION": 5, "PARTIAL": -10, "CLOSED": -30}.get(gate_status, -30)

        # Fragility penalty
        frag_penalty = frag_score * 0.3

        # Regime factor
        regime_bonus = {"normal": 10, "event": -5, "spike": -20, "blocked": -40}.get(regime, -10)

        composite_confidence = signal_confidence + gate_bonus - frag_penalty + regime_bonus
        composite_confidence = max(0, min(100, composite_confidence))

        # Check threshold
        if composite_confidence < self.min_confidence:
            return None

        # Determine direction from signal
        score_val = signal_score.get("score", 0)
        if abs(score_val) < 15:  # Too weak, no clear direction
            return None

        direction = TradeDirection.LONG if score_val > 0 else TradeDirection.SHORT

        # Check cooldown for this direction
        cooldown_key = f"{symbol}_{direction.value}"
        if cooldown_key in self._recent_signals:
            elapsed = (datetime.now(timezone.utc) - self._recent_signals[cooldown_key]).total_seconds()
            if elapsed < self._signal_cooldown_sec:
                return None

        # Calculate entry, stop loss, take profit
        safe_atr = max(0.1, atr)

        if direction == TradeDirection.LONG:
            entry_price = current_price
            stop_loss = round(entry_price - safe_atr * 1.5, 2)
            take_profit_1 = round(entry_price + safe_atr * 2.0, 2)
            take_profit_2 = round(entry_price + safe_atr * 3.5, 2)
        else:
            entry_price = current_price
            stop_loss = round(entry_price + safe_atr * 1.5, 2)
            take_profit_1 = round(entry_price - safe_atr * 2.0, 2)
            take_profit_2 = round(entry_price - safe_atr * 3.5, 2)

        # Position size based on risk
        risk_per_contract = abs(entry_price - stop_loss) * 1000
        equity = risk_control.get("equity", {}).get("current", 50000)
        max_risk = equity * 0.01  # 1% risk per trade
        size = max(1, int(max_risk / max(1, risk_per_contract)))

        # Build reasoning
        zone = signal_score.get("zone", "")
        components = signal_score.get("components", {})
        top_factors = sorted(components.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        factors_text = ", ".join([f"{k}: {'+' if v>0 else ''}{v:.1f}" for k, v in top_factors])

        reasoning = (
            f"{'做多' if direction == TradeDirection.LONG else '做空'}{symbol} | "
            f"综合置信度 {composite_confidence:.0f}% | "
            f"信号区: {zone} | "
            f"门控: {gate_status} | "
            f"主要因子: {factors_text}"
        )

        # Exit tiers
        max_loss_per_unit = abs(entry_price - stop_loss)
        exit_tiers = [
            {"tier": "WARNING", "mult": "-50%", "price": round(entry_price + (-1 if direction == TradeDirection.LONG else 1) * max_loss_per_unit * 0.5, 2), "action": "预警通知"},
            {"tier": "PRE_REDUCE", "mult": "-70%", "price": round(entry_price + (-1 if direction == TradeDirection.LONG else 1) * max_loss_per_unit * 0.7, 2), "action": "减仓50%"},
            {"tier": "MAIN_STOP", "mult": "-100%", "price": stop_loss, "action": "全部平仓"},
            {"tier": "DISASTER", "mult": "-150%", "price": round(entry_price + (-1 if direction == TradeDirection.LONG else 1) * max_loss_per_unit * 1.5, 2), "action": "灾难保护"},
        ]

        opp = TradeOpportunity(
            id=f"opp_{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            direction=direction,
            confidence=composite_confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            size=size,
            reasoning=reasoning,
            signal_components=components,
            gate_status=gate_status,
            fragility_score=frag_score,
            regime=regime,
            exit_tiers=exit_tiers,
        )

        self._opportunities[opp.id] = opp
        self._recent_signals[cooldown_key] = datetime.now(timezone.utc)

        # Send notification
        if self._notification_callback:
            await self._notification_callback(opp)

        logger.info(f"[Bot] Opportunity generated: {opp.id} {direction.value} {symbol} @ {entry_price} confidence={composite_confidence:.0f}%")
        return opp

    def approve_opportunity(self, opportunity_id: str) -> Optional[Dict]:
        """User approves a trade opportunity"""
        opp = self._opportunities.get(opportunity_id)
        if not opp:
            return None
        if opp.status != OpportunityStatus.PENDING:
            return {"error": f"Opportunity is {opp.status.value}, cannot approve"}

        # Check if expired
        expires = datetime.fromisoformat(opp.expires_at)
        if datetime.now(timezone.utc) > expires:
            opp.status = OpportunityStatus.EXPIRED
            return {"error": "Opportunity has expired"}

        opp.status = OpportunityStatus.APPROVED
        opp.acted_at = datetime.now(timezone.utc).isoformat()
        return opp.to_dict()

    def reject_opportunity(self, opportunity_id: str) -> Optional[Dict]:
        """User rejects a trade opportunity"""
        opp = self._opportunities.get(opportunity_id)
        if not opp:
            return None
        if opp.status != OpportunityStatus.PENDING:
            return {"error": f"Opportunity is {opp.status.value}"}

        opp.status = OpportunityStatus.REJECTED
        opp.acted_at = datetime.now(timezone.utc).isoformat()
        self._history.append(opp)
        return opp.to_dict()

    def mark_executed(self, opportunity_id: str, position_id: str):
        """Mark opportunity as executed after broker fills"""
        opp = self._opportunities.get(opportunity_id)
        if opp:
            opp.status = OpportunityStatus.EXECUTED
            opp.position_id = position_id
            self._daily_trade_count += 1
            self._history.append(opp)

    def _expire_old_opportunities(self):
        """Expire opportunities past their TTL"""
        now = datetime.now(timezone.utc)
        for opp_id, opp in list(self._opportunities.items()):
            if opp.status == OpportunityStatus.PENDING:
                try:
                    expires = datetime.fromisoformat(opp.expires_at)
                    if now > expires:
                        opp.status = OpportunityStatus.EXPIRED
                        self._history.append(opp)
                except (ValueError, TypeError):
                    pass

    def get_pending_opportunities(self) -> List[Dict]:
        """Get all pending opportunities"""
        self._expire_old_opportunities()
        return [
            opp.to_dict()
            for opp in self._opportunities.values()
            if opp.status == OpportunityStatus.PENDING
        ]

    def get_history(self, limit: int = 20) -> List[Dict]:
        """Get opportunity history"""
        return [opp.to_dict() for opp in self._history[-limit:]]

    def get_status(self) -> Dict:
        """Get bot status summary"""
        pending = sum(1 for o in self._opportunities.values() if o.status == OpportunityStatus.PENDING)
        executed_today = self._daily_trade_count
        total_generated = len(self._opportunities) + len(self._history)
        total_approved = sum(1 for o in self._history if o.status in (OpportunityStatus.EXECUTED, OpportunityStatus.APPROVED))
        total_rejected = sum(1 for o in self._history if o.status == OpportunityStatus.REJECTED)

        return {
            "enabled": self.enabled,
            "min_confidence": self.min_confidence,
            "scan_interval_sec": self.scan_interval_sec,
            "max_daily_trades": self.max_daily_trades,
            "pending_count": pending,
            "executed_today": executed_today,
            "remaining_today": max(0, self.max_daily_trades - executed_today),
            "total_generated": total_generated,
            "total_approved": total_approved,
            "total_rejected": total_rejected,
            "last_scan": self._last_scan_time,
        }


# Global instance
trading_bot = TradingBot()
