"""
Security Integration for AI Bond Trading System
Integrates shared security modules with the Interest Rate/Bond trading platform.
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


class BondSecurityIntegration:
    """
    Security integration layer for AI Bond Trading System.
    Tailored for fixed income trading with appropriate risk limits.
    """
    
    def __init__(self, mongodb_db):
        """
        Initialize Bond security integration.
        
        Args:
            mongodb_db: MongoDB database instance
        """
        self.db = mongodb_db
        
        # Initialize with bond-appropriate policies
        self.risk_engine = RiskEngine(
            policies=RiskPolicies(
                max_single_trade_notional_usd=200000.0,  # Bonds typically larger
                max_daily_loss_usd=-10000.0,
                max_weekly_loss_usd=-30000.0,
                max_gross_exposure_usd=1000000.0,  # Higher for bonds
                max_spread_bps=2.0,  # Bonds have tight spreads
                max_quote_age_ms=1000,  # Less time-sensitive than FX
                max_volatility_ratio=2.5,
                kill_switch_max_drawdown_pct=5.0,  # More conservative
                kill_switch_consecutive_losses=3
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
        
        logger.info("Bond Security Integration initialized")
        self._initialized = True
    
    async def close(self) -> None:
        """Close all connections."""
        await self.audit_service.close()
        await self.idempotency_service.close()
        await self.order_ledger.close()
        await self.forwarder.close()
    
    async def evaluate_signal_intent(
        self,
        signal_type: str,
        desired_quantity: int,
        confidence: float,
        portfolio_state: dict,
        market_data: dict,
        strategy: str = "AI_HYBRID"
    ) -> IntentEvaluationResponse:
        """
        Evaluate bond trading signal against risk policies.
        
        Args:
            signal_type: Signal type (BOND_BUY, BOND_SELL, RATE_LONG, RATE_SHORT)
            desired_quantity: Desired quantity
            confidence: Signal confidence (0-1)
            portfolio_state: Current portfolio state
            market_data: Current market data
            strategy: Trading strategy name
            
        Returns:
            Intent evaluation response
        """
        # Determine asset and side from signal type
        if "BOND" in signal_type:
            symbol = "10Y_BOND"
            side = "BUY" if "BUY" in signal_type else "SELL"
            price = market_data.get("bond_yield", 4.5)
            # Calculate notional based on bond price (simplified)
            notional_usd = desired_quantity * price * 1000  # Face value assumption
        else:
            symbol = "RATE_FUTURES"
            side = "BUY" if "LONG" in signal_type else "SELL"
            price = market_data.get("wti_price", 75)  # Using WTI as proxy
            notional_usd = desired_quantity * price * 100
        
        # Build portfolio snapshot
        portfolio_snapshot = PortfolioSnapshot(
            daily_pnl_usd=portfolio_state.get("daily_pnl", 0.0),
            weekly_pnl_usd=portfolio_state.get("weekly_pnl", 0.0),
            gross_exposure_usd=portfolio_state.get("total_exposure", 0.0),
            net_exposure_usd=portfolio_state.get("net_exposure", 0.0),
            open_positions_count=len(portfolio_state.get("positions", [])),
            consecutive_losses=portfolio_state.get("consecutive_losses", 0),
            current_drawdown_pct=portfolio_state.get("drawdown_pct", 0.0),
            current_equity_usd=portfolio_state.get("total_value", 100000.0)
        )
        
        # Build market snapshot
        market_snapshot = MarketSnapshot(
            symbol=symbol,
            bid=price * 0.9999,  # Approximate bid
            ask=price * 1.0001,  # Approximate ask
            spread_bps=2.0,  # Assume 2 bps for bonds
            quote_age_ms=market_data.get("quote_age_ms", 100),
            volatility_ratio=market_data.get("volatility_ratio", 1.0),
            regime=market_data.get("regime", "NORMAL"),
            exchange_incident_flag=False,
            network_incident_flag=False
        )
        
        # Create evaluation request
        request = IntentEvaluationRequest(
            model_name="AI-Bond-Trading",
            model_version="5.0.0",
            symbol=symbol,
            side=OrderSide(side),
            desired_notional_usd=notional_usd,
            portfolio_snapshot=portfolio_snapshot,
            market_snapshot=market_snapshot
        )
        
        # Evaluate
        response = self.risk_engine.evaluate_intent(request)
        
        # Apply confidence-based adjustment
        if response.approved and confidence < 0.7:
            response.warnings.append("LOW_CONFIDENCE_SIGNAL")
        
        # Log to audit
        await self.audit_service.log_risk_decision(request, response)
        
        return response
    
    async def process_signal_execution(
        self,
        signal_id: str,
        signal_type: str,
        quantity: int,
        execution_price: float,
        portfolio_state: dict,
        market_data: dict
    ) -> dict:
        """
        Process signal execution with full security checks.
        
        Args:
            signal_id: Signal identifier
            signal_type: Signal type
            quantity: Quantity to execute
            execution_price: Execution price
            portfolio_state: Portfolio state
            market_data: Market data
            
        Returns:
            Execution result dict
        """
        # Check idempotency
        existing = await self.idempotency_service.get(signal_id)
        if existing:
            return {
                "status": "DUPLICATE",
                "message": "Signal already processed",
                "existing_response": existing.model_dump()
            }
        
        # Evaluate intent
        evaluation = await self.evaluate_signal_intent(
            signal_type=signal_type,
            desired_quantity=quantity,
            confidence=0.8,  # Default confidence
            portfolio_state=portfolio_state,
            market_data=market_data
        )
        
        if not evaluation.approved:
            return {
                "status": "REJECTED",
                "message": "Risk check failed",
                "reasons": evaluation.reject_reason_codes,
                "risk_score": evaluation.risk_score
            }
        
        # Store in ledger
        from shared_security.models import OrderRequest, OrderResponse
        
        order_request = OrderRequest(
            request_id=evaluation.request_id,
            client_order_id=signal_id,
            symbol=evaluation.approved_order.symbol if evaluation.approved_order else "10Y_BOND",
            side=evaluation.approved_order.side if evaluation.approved_order else OrderSide.BUY,
            order_type=evaluation.approved_order.order_type if evaluation.approved_order else "MARKET",
            quantity=evaluation.approved_order.quantity if evaluation.approved_order else quantity,
            limit_price=execution_price,
            applied_policy_version=evaluation.applied_policy_version
        )
        
        await self.order_ledger.insert_new(order_request)
        
        # Create response
        order_response = OrderResponse(
            request_id=evaluation.request_id,
            client_order_id=signal_id,
            broker_order_id=f"bond-{signal_id}",
            status=OrderStatus.FILLED,
            filled_quantity=quantity,
            filled_price=execution_price
        )
        
        await self.order_ledger.update_from_response(order_response)
        await self.idempotency_service.put(signal_id, order_response)
        
        return {
            "status": "EXECUTED",
            "message": "Order executed successfully",
            "order_id": signal_id,
            "filled_quantity": quantity,
            "filled_price": execution_price,
            "policy_version": evaluation.applied_policy_version
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
    
    async def get_order_history(self, symbol: Optional[str] = None, limit: int = 50) -> list:
        """Get order history from ledger."""
        records = await self.order_ledger.get_order_history(symbol=symbol, limit=limit)
        return [r.model_dump() for r in records]
    
    async def get_open_orders(self) -> list:
        """Get open orders from ledger."""
        records = await self.order_ledger.list_open_orders()
        return [r.model_dump() for r in records]


# Singleton
_bond_security: Optional[BondSecurityIntegration] = None


def get_bond_security_integration(mongodb_db) -> BondSecurityIntegration:
    """Get or create Bond security integration."""
    global _bond_security
    if _bond_security is None:
        _bond_security = BondSecurityIntegration(mongodb_db)
    return _bond_security
