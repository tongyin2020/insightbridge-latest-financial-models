"""
Security Integration for WTI Crude Oil AI Trading Platform
Integrates shared security modules with the Oil trading platform.
"""
import os
import sys
import logging
from typing import Optional
from datetime import datetime, timezone

# Add shared_security to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared_security'))

from shared_security import (
    RiskEngine, AuditService, IdempotencyService, OrderLedger, SecureForwarder,
    HMACAuth, RiskPolicies, CURRENT_POLICY_VERSION,
    IntentEvaluationRequest, IntentEvaluationResponse, ApprovedOrder,
    PortfolioSnapshot, MarketSnapshot, OrderSide, OrderStatus
)

logger = logging.getLogger(__name__)


class OilSecurityIntegration:
    """
    Security integration layer for WTI Crude Oil AI Trading Platform.
    Tailored for commodity futures trading with appropriate risk limits.
    """
    
    def __init__(self, mongodb_db):
        """
        Initialize Oil security integration.
        
        Args:
            mongodb_db: MongoDB database instance
        """
        self.db = mongodb_db
        
        # Initialize with oil/commodity-appropriate policies
        self.risk_engine = RiskEngine(
            policies=RiskPolicies(
                max_single_trade_notional_usd=50000.0,
                max_daily_loss_usd=-5000.0,
                max_weekly_loss_usd=-15000.0,
                max_gross_exposure_usd=200000.0,
                max_spread_bps=10.0,  # Oil can have wider spreads
                max_quote_age_ms=500,
                max_volatility_ratio=3.0,  # Oil is more volatile
                kill_switch_max_drawdown_pct=10.0,
                kill_switch_consecutive_losses=4
            )
        )
        
        self.audit_service = AuditService(
            postgres_url=os.environ.get("POSTGRES_URL"),
            mongodb_db=mongodb_db,
            use_postgres=bool(os.environ.get("POSTGRES_URL"))
        )
        
        self.idempotency_service = IdempotencyService(
            redis_url=os.environ.get("REDIS_URL"),
            mongodb_db=mongodb_db
        )
        
        self.order_ledger = OrderLedger(
            postgres_url=os.environ.get("POSTGRES_URL"),
            mongodb_db=mongodb_db,
            use_postgres=bool(os.environ.get("POSTGRES_URL"))
        )
        
        self.hmac_auth = HMACAuth(
            secret=os.environ.get("INTERNAL_SIGNING_SECRET"),
            required=bool(os.environ.get("INTERNAL_SIGNING_SECRET"))
        )
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all security services."""
        if self._initialized:
            return
        
        await self.audit_service.initialize()
        await self.idempotency_service.initialize()
        await self.order_ledger.initialize()
        
        logger.info("Oil Security Integration initialized")
        self._initialized = True
    
    async def close(self) -> None:
        """Close all connections."""
        await self.audit_service.close()
        await self.idempotency_service.close()
        await self.order_ledger.close()
    
    async def evaluate_trade_opportunity(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        confidence: float,
        risk_state: dict,
        market_indicators: dict,
        fragility_state: dict
    ) -> IntentEvaluationResponse:
        """
        Evaluate oil trading opportunity against risk policies.
        
        Args:
            symbol: Asset symbol (CL, WTI, etc.)
            direction: Direction (long/short)
            entry_price: Entry price
            quantity: Quantity
            confidence: Signal confidence
            risk_state: Risk service state
            market_indicators: Market indicators
            fragility_state: Fragility engine state
            
        Returns:
            Intent evaluation response
        """
        # Calculate notional
        notional_usd = quantity * entry_price * 1000  # Oil futures multiplier
        
        # Map direction to side
        side = OrderSide.BUY if direction.lower() == "long" else OrderSide.SELL
        
        # Build portfolio snapshot from risk state
        portfolio_snapshot = PortfolioSnapshot(
            daily_pnl_usd=risk_state.get("daily_pnl", 0.0),
            weekly_pnl_usd=risk_state.get("weekly_pnl", 0.0),
            gross_exposure_usd=risk_state.get("gross_exposure", 0.0),
            open_positions_count=risk_state.get("open_positions_count", 0),
            consecutive_losses=risk_state.get("consecutive_losses", 0),
            current_drawdown_pct=risk_state.get("drawdown_pct", 0.0),
            current_equity_usd=risk_state.get("equity", 100000.0)
        )
        
        # Build market snapshot
        spread = market_indicators.get("spread", 0.03)
        spread_bps = (spread / entry_price) * 10000 if entry_price > 0 else 0
        
        # Factor in fragility score
        fragility_score = fragility_state.get("score", 0)
        volatility_ratio = market_indicators.get("volatility_ratio", 1.0)
        
        # Increase volatility ratio based on fragility
        if fragility_score > 70:
            volatility_ratio *= 1.5
        elif fragility_score > 50:
            volatility_ratio *= 1.2
        
        market_snapshot = MarketSnapshot(
            symbol=symbol,
            bid=entry_price - spread / 2,
            ask=entry_price + spread / 2,
            spread_bps=spread_bps,
            quote_age_ms=int(market_indicators.get("quote_age_ms", 100)),
            volatility_ratio=volatility_ratio,
            regime=market_indicators.get("regime", "NORMAL"),
            exchange_incident_flag=False,
            network_incident_flag=False
        )
        
        # Create evaluation request
        request = IntentEvaluationRequest(
            model_name="WTI-Oil-Trading",
            model_version="2.0.0",
            symbol=symbol,
            side=side,
            desired_notional_usd=notional_usd,
            portfolio_snapshot=portfolio_snapshot,
            market_snapshot=market_snapshot
        )
        
        # Evaluate
        response = self.risk_engine.evaluate_intent(request)
        
        # Add fragility-based warnings
        if fragility_score > 70:
            response.warnings.append("HIGH_FRAGILITY_MARKET")
        if confidence < 60:
            response.warnings.append("LOW_CONFIDENCE_SIGNAL")
        
        # Log to audit
        await self.audit_service.log_risk_decision(request, response)
        
        return response
    
    async def validate_bot_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        signal_score: dict,
        execution_gate: dict,
        fragility: dict,
        risk_control: dict,
        regime: str,
        atr: float
    ) -> dict:
        """
        Validate automated bot trade with security layer.
        
        Args:
            symbol: Asset symbol
            direction: Trade direction
            entry_price: Entry price
            signal_score: Signal scoring result
            execution_gate: Execution gate result
            fragility: Fragility state
            risk_control: Risk control state
            regime: Market regime
            atr: ATR value
            
        Returns:
            Validation result dict
        """
        # Calculate quantity based on ATR and risk
        risk_per_trade = 500  # $500 risk per trade
        stop_distance = atr * 2
        quantity = risk_per_trade / (stop_distance * 1000) if stop_distance > 0 else 0.1
        
        # Evaluate through security layer
        confidence = signal_score.get("bullish_pct", 50) if direction == "long" else signal_score.get("bearish_pct", 50)
        
        evaluation = await self.evaluate_trade_opportunity(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            confidence=confidence,
            risk_state=risk_control,
            market_indicators={
                "spread": execution_gate.get("spread", 0.03),
                "volatility_ratio": execution_gate.get("vol_ratio", 1.0),
                "regime": regime
            },
            fragility_state=fragility
        )
        
        # Combine with execution gate
        gate_allowed = execution_gate.get("allowed", False)
        
        result = {
            "allowed": evaluation.approved and gate_allowed,
            "security_approved": evaluation.approved,
            "gate_approved": gate_allowed,
            "decision": evaluation.decision,
            "risk_score": evaluation.risk_score,
            "reject_reasons": evaluation.reject_reason_codes,
            "warnings": evaluation.warnings,
            "policy_version": evaluation.applied_policy_version
        }
        
        if evaluation.approved and evaluation.approved_order:
            result["approved_quantity"] = evaluation.approved_order.quantity
            result["approved_notional"] = evaluation.approved_order.adjusted_notional_usd
        
        return result
    
    async def record_trade_execution(
        self,
        trade_id: str,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: dict
    ) -> dict:
        """
        Record trade execution to ledger with idempotency.
        
        Args:
            trade_id: Unique trade ID
            symbol: Asset symbol
            direction: Trade direction
            quantity: Executed quantity
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit_levels: Take profit levels
            
        Returns:
            Recording result
        """
        # Check idempotency
        existing = await self.idempotency_service.get(trade_id)
        if existing:
            return {
                "status": "DUPLICATE",
                "existing_order": existing.model_dump()
            }
        
        from shared_security.models import OrderRequest, OrderResponse
        
        # Create and record order
        side = OrderSide.BUY if direction.lower() == "long" else OrderSide.SELL
        
        order_request = OrderRequest(
            request_id=f"oil-{trade_id}",
            client_order_id=trade_id,
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            limit_price=entry_price,
            applied_policy_version=CURRENT_POLICY_VERSION
        )
        
        await self.order_ledger.insert_new(order_request)
        
        order_response = OrderResponse(
            request_id=f"oil-{trade_id}",
            client_order_id=trade_id,
            broker_order_id=f"broker-{trade_id}",
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            filled_price=entry_price
        )
        
        await self.order_ledger.update_from_response(order_response)
        await self.idempotency_service.put(trade_id, order_response)
        
        # Log execution
        await self.audit_service.log_execution(
            request_id=f"oil-{trade_id}",
            client_order_id=trade_id,
            broker_order_id=f"broker-{trade_id}",
            symbol=symbol,
            side=side.value,
            order_type="MARKET",
            quantity=quantity,
            limit_price=entry_price,
            status="FILLED",
            policy_version=CURRENT_POLICY_VERSION,
            filled_quantity=quantity,
            filled_price=entry_price
        )
        
        return {
            "status": "RECORDED",
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "quantity": quantity,
            "entry_price": entry_price
        }
    
    def get_risk_status(self) -> dict:
        """Get current risk engine status."""
        return self.risk_engine.get_status()
    
    def is_trading_halted(self) -> bool:
        """Check if trading is halted."""
        return self.risk_engine.is_halted
    
    async def reset_kill_switch(self, reset_by: str, reason: str) -> bool:
        """Reset kill switch."""
        return self.risk_engine.reset_kill_switch(reset_by, reason)
    
    async def get_trade_history(self, symbol: Optional[str] = None, limit: int = 50) -> list:
        """Get trade history from ledger."""
        records = await self.order_ledger.get_order_history(symbol=symbol, limit=limit)
        return [r.model_dump() for r in records]


# Singleton
_oil_security: Optional[OilSecurityIntegration] = None


def get_oil_security_integration(mongodb_db) -> OilSecurityIntegration:
    """Get or create Oil security integration."""
    global _oil_security
    if _oil_security is None:
        _oil_security = OilSecurityIntegration(mongodb_db)
    return _oil_security
