"""
Security Integration for FX Trading System (AUD/USD, NZD/USD)
Integrates shared security modules with the Foreign Currency trading platform.
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


class FXSecurityIntegration:
    """
    Security integration layer for FX Trading System.
    Tailored for forex trading with appropriate leverage and spread limits.
    """
    
    def __init__(self, mongodb_db):
        """
        Initialize FX security integration.
        
        Args:
            mongodb_db: MongoDB database instance
        """
        self.db = mongodb_db
        
        # Initialize with FX-appropriate policies
        self.risk_engine = RiskEngine(
            policies=RiskPolicies(
                max_single_trade_notional_usd=100000.0,  # FX allows larger positions
                max_daily_loss_usd=-5000.0,
                max_weekly_loss_usd=-15000.0,
                max_gross_exposure_usd=500000.0,  # Higher for FX
                max_spread_bps=3.0,  # FX has tighter spreads
                max_quote_age_ms=300,  # Faster quotes required
                kill_switch_max_drawdown_pct=8.0,
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
        
        self.forwarder = SecureForwarder(
            execution_service_url=os.environ.get("EXECUTION_SERVICE_URL"),
            signing_secret=os.environ.get("INTERNAL_SIGNING_SECRET")
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
        
        logger.info("FX Security Integration initialized")
        self._initialized = True
    
    async def close(self) -> None:
        """Close all connections."""
        await self.audit_service.close()
        await self.idempotency_service.close()
        await self.order_ledger.close()
        await self.forwarder.close()
    
    async def evaluate_trade_intent(
        self,
        pair: str,
        side: str,
        desired_notional_usd: float,
        risk_control_state: dict,
        market_data: dict
    ) -> IntentEvaluationResponse:
        """
        Evaluate FX trading intent against risk policies.
        
        Args:
            pair: Currency pair (AUD/USD, NZD/USD)
            side: Order side (BUY or SELL)
            desired_notional_usd: Desired notional amount
            risk_control_state: Risk control system state
            market_data: Current market data
            
        Returns:
            Intent evaluation response
        """
        # Build portfolio snapshot from risk control state
        daily_stats = risk_control_state.get("daily_stats", {})
        weekly_stats = risk_control_state.get("weekly_stats", {})
        
        portfolio_snapshot = PortfolioSnapshot(
            daily_pnl_usd=daily_stats.get("total_pnl_pips", 0) * 10,  # Convert pips to USD approx
            weekly_pnl_usd=weekly_stats.get("total_pnl_pips", 0) * 10,
            gross_exposure_usd=risk_control_state.get("gross_exposure_usd", 0.0),
            open_positions_count=risk_control_state.get("open_positions_count", 0),
            consecutive_losses=daily_stats.get("consecutive_losses", 0),
            current_drawdown_pct=daily_stats.get("max_drawdown_pips", 0) / 100,
            current_equity_usd=daily_stats.get("current_equity", 10000.0)
        )
        
        # Build market snapshot
        spread_pips = market_data.get("spread_pips", 0)
        spread_bps = spread_pips  # For FX, pips ≈ bps
        
        market_snapshot = MarketSnapshot(
            symbol=pair,
            bid=market_data.get("bid", 0),
            ask=market_data.get("ask", 0),
            spread_bps=spread_bps,
            quote_age_ms=int(market_data.get("quote_age_ms", 0)),
            volatility_ratio=market_data.get("vol_ratio", 1.0),
            regime=market_data.get("regime", "NORMAL"),
            exchange_incident_flag=False,
            network_incident_flag=False
        )
        
        # Create evaluation request
        request = IntentEvaluationRequest(
            model_name="FX-Trading-System",
            model_version="1.0.0",
            symbol=pair,
            side=OrderSide(side.upper()),
            desired_notional_usd=desired_notional_usd,
            portfolio_snapshot=portfolio_snapshot,
            market_snapshot=market_snapshot
        )
        
        # Evaluate
        response = self.risk_engine.evaluate_intent(request)
        
        # Log to audit
        await self.audit_service.log_risk_decision(request, response)
        
        return response
    
    async def check_entry_with_security(
        self,
        pair: str,
        direction: str,
        spread_pips: float,
        risk_control_state: dict,
        market_data: dict,
        notional_usd: float = 10000.0
    ) -> dict:
        """
        Enhanced entry check combining existing risk control with security layer.
        
        Args:
            pair: Currency pair
            direction: Trade direction
            spread_pips: Current spread
            risk_control_state: Risk control state
            market_data: Market data
            notional_usd: Desired notional
            
        Returns:
            Combined entry check result
        """
        # First, evaluate through security layer
        security_eval = await self.evaluate_trade_intent(
            pair=pair,
            side=direction,
            desired_notional_usd=notional_usd,
            risk_control_state=risk_control_state,
            market_data=market_data
        )
        
        result = {
            "allowed": security_eval.approved,
            "security_approved": security_eval.approved,
            "security_decision": security_eval.decision,
            "security_reasons": security_eval.reject_reason_codes,
            "security_warnings": security_eval.warnings,
            "risk_score": security_eval.risk_score,
            "policy_version": security_eval.applied_policy_version,
            "adjusted_size_ratio": 1.0
        }
        
        # If security approved, check for size adjustments
        if security_eval.approved and security_eval.approved_order:
            if security_eval.approved_order.size_adjusted:
                original = security_eval.approved_order.original_notional_usd or notional_usd
                adjusted = security_eval.approved_order.adjusted_notional_usd or notional_usd
                result["adjusted_size_ratio"] = adjusted / original if original > 0 else 1.0
                result["approved_order"] = security_eval.approved_order.model_dump()
        
        return result
    
    def get_risk_status(self) -> dict:
        """Get current risk engine status."""
        return self.risk_engine.get_status()
    
    def is_trading_halted(self) -> bool:
        """Check if trading is halted."""
        return self.risk_engine.is_halted
    
    async def reset_kill_switch(self, reset_by: str, reason: str) -> bool:
        """Reset kill switch."""
        return self.risk_engine.reset_kill_switch(reset_by, reason)
    
    async def get_audit_history(self, pair: Optional[str] = None, limit: int = 50) -> list:
        """Get audit history."""
        return await self.audit_service.get_audit_history(symbol=pair, limit=limit)


# Singleton
_fx_security: Optional[FXSecurityIntegration] = None


def get_fx_security_integration(mongodb_db) -> FXSecurityIntegration:
    """Get or create FX security integration."""
    global _fx_security
    if _fx_security is None:
        _fx_security = FXSecurityIntegration(mongodb_db)
    return _fx_security
