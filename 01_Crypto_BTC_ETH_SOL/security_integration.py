"""
Security Integration for Crypto AI Trading System
Integrates shared security modules with the existing Crypto trading platform.
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


class CryptoSecurityIntegration:
    """
    Security integration layer for Crypto AI Trading System.
    Provides risk evaluation, audit logging, idempotency, and order management.
    """
    
    def __init__(self, mongodb_db):
        """
        Initialize security integration.
        
        Args:
            mongodb_db: MongoDB database instance
        """
        self.db = mongodb_db
        
        # Initialize security components
        self.risk_engine = RiskEngine(
            policies=RiskPolicies(
                max_single_trade_notional_usd=50000.0,  # Higher for crypto
                max_daily_loss_usd=-10000.0,
                max_spread_bps=15.0,  # Crypto has wider spreads
                kill_switch_max_drawdown_pct=15.0
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
        
        logger.info("Crypto Security Integration initialized")
        self._initialized = True
    
    async def close(self) -> None:
        """Close all connections."""
        await self.audit_service.close()
        await self.idempotency_service.close()
        await self.order_ledger.close()
    
    async def evaluate_trade_intent(
        self,
        symbol: str,
        side: str,
        desired_notional_usd: float,
        portfolio_state: dict,
        market_state: dict
    ) -> IntentEvaluationResponse:
        """
        Evaluate trading intent against risk policies.
        
        Args:
            symbol: Trading symbol (BTC, ETH, SOL, etc.)
            side: Order side (BUY or SELL)
            desired_notional_usd: Desired notional amount
            portfolio_state: Current portfolio state dict
            market_state: Current market state dict
            
        Returns:
            Intent evaluation response
        """
        # Build portfolio snapshot
        portfolio_snapshot = PortfolioSnapshot(
            daily_pnl_usd=portfolio_state.get("daily_pnl_usd", 0.0),
            weekly_pnl_usd=portfolio_state.get("weekly_pnl_usd", 0.0),
            gross_exposure_usd=portfolio_state.get("gross_exposure_usd", 0.0),
            net_exposure_usd=portfolio_state.get("net_exposure_usd", 0.0),
            open_positions_count=portfolio_state.get("open_positions_count", 0),
            consecutive_losses=portfolio_state.get("consecutive_losses", 0),
            current_drawdown_pct=portfolio_state.get("current_drawdown_pct", 0.0),
            current_equity_usd=portfolio_state.get("current_equity_usd", 10000.0)
        )
        
        # Build market snapshot
        bid = market_state.get("bid", market_state.get("price", 0))
        ask = market_state.get("ask", market_state.get("price", 0))
        spread_bps = ((ask - bid) / bid * 10000) if bid > 0 else 0
        
        market_snapshot = MarketSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            spread_bps=spread_bps,
            quote_age_ms=market_state.get("quote_age_ms", 0),
            volatility_ratio=market_state.get("volatility_ratio", 1.0),
            regime=market_state.get("regime", "NORMAL"),
            exchange_incident_flag=market_state.get("exchange_incident_flag", False),
            network_incident_flag=market_state.get("network_incident_flag", False)
        )
        
        # Create evaluation request
        request = IntentEvaluationRequest(
            model_name="Crypto-AI-Trading",
            model_version="1.0.0",
            symbol=symbol,
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
    
    async def check_idempotency(self, client_order_id: str):
        """Check if order was already processed."""
        return await self.idempotency_service.get(client_order_id)
    
    async def record_order(self, order_request, order_response):
        """Record order to ledger and idempotency cache."""
        await self.order_ledger.insert_new(order_request)
        await self.order_ledger.update_from_response(order_response)
        await self.idempotency_service.put(
            order_request.client_order_id,
            order_response
        )
    
    def get_risk_status(self) -> dict:
        """Get current risk engine status."""
        return self.risk_engine.get_status()
    
    def is_trading_halted(self) -> bool:
        """Check if trading is halted by kill switch."""
        return self.risk_engine.is_halted
    
    async def reset_kill_switch(self, reset_by: str, reason: str) -> bool:
        """Reset kill switch manually."""
        return self.risk_engine.reset_kill_switch(reset_by, reason)


# Singleton instance
_security_integration: Optional[CryptoSecurityIntegration] = None


def get_security_integration(mongodb_db) -> CryptoSecurityIntegration:
    """Get or create security integration instance."""
    global _security_integration
    if _security_integration is None:
        _security_integration = CryptoSecurityIntegration(mongodb_db)
    return _security_integration
