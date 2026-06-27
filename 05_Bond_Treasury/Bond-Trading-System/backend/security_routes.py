"""
Security API Routes for AI Bond Trading System
Provides REST endpoints for risk management, audit, and security features.
"""
import os
import sys
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

# Add shared_security to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared_security'))

from security_integration import get_bond_security_integration, BondSecurityIntegration

bond_security_router = APIRouter(prefix="/api/security", tags=["Security"])


class BondSignalIntentRequest(BaseModel):
    signal_type: str  # BOND_BUY, BOND_SELL, RATE_LONG, RATE_SHORT
    desired_quantity: int
    confidence: float = 0.8
    portfolio_state: Optional[dict] = None
    market_data: Optional[dict] = None
    strategy: str = "AI_HYBRID"


class BondExecutionRequest(BaseModel):
    signal_id: str
    signal_type: str
    quantity: int
    execution_price: float
    portfolio_state: Optional[dict] = None
    market_data: Optional[dict] = None


class KillSwitchResetRequest(BaseModel):
    reset_by: str
    reason: str


# Global security instance
_bond_security: Optional[BondSecurityIntegration] = None


def set_bond_security_instance(security: BondSecurityIntegration):
    """Set the global Bond security instance."""
    global _bond_security
    _bond_security = security


def get_bond_security() -> BondSecurityIntegration:
    """Get the Bond security instance."""
    if _bond_security is None:
        raise HTTPException(status_code=500, detail="Bond Security service not initialized")
    return _bond_security


@bond_security_router.get("/status")
async def get_bond_security_status():
    """Get current bond trading security/risk status."""
    security = get_bond_security()
    status = security.get_risk_status()
    return {
        "status": "ok",
        "risk_status": status,
        "trading_halted": security.is_trading_halted(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@bond_security_router.post("/evaluate-signal")
async def evaluate_bond_signal_intent(request: BondSignalIntentRequest):
    """
    Evaluate a bond trading signal against risk policies.
    """
    security = get_bond_security()
    
    portfolio_state = request.portfolio_state or {
        "daily_pnl": 0,
        "total_value": 100000,
        "positions": []
    }
    
    market_data = request.market_data or {
        "bond_yield": 4.5,
        "wti_price": 75,
        "volatility_ratio": 1.0,
        "regime": "NORMAL"
    }
    
    result = await security.evaluate_signal_intent(
        signal_type=request.signal_type,
        desired_quantity=request.desired_quantity,
        confidence=request.confidence,
        portfolio_state=portfolio_state,
        market_data=market_data,
        strategy=request.strategy
    )
    
    return {
        "approved": result.approved,
        "decision": result.decision,
        "risk_score": result.risk_score,
        "reject_reasons": result.reject_reason_codes,
        "warnings": result.warnings,
        "policy_version": result.applied_policy_version,
        "approved_order": result.approved_order.model_dump() if result.approved_order else None
    }


@bond_security_router.post("/execute-signal")
async def execute_bond_signal(request: BondExecutionRequest):
    """
    Execute a bond trading signal with full security checks.
    Includes idempotency and ledger recording.
    """
    security = get_bond_security()
    
    portfolio_state = request.portfolio_state or {}
    market_data = request.market_data or {"bond_yield": request.execution_price}
    
    result = await security.process_signal_execution(
        signal_id=request.signal_id,
        signal_type=request.signal_type,
        quantity=request.quantity,
        execution_price=request.execution_price,
        portfolio_state=portfolio_state,
        market_data=market_data
    )
    
    return result


@bond_security_router.get("/kill-switch")
async def get_bond_kill_switch_status():
    """Get kill switch status."""
    security = get_bond_security()
    return {
        "active": security.is_trading_halted(),
        "status": security.get_risk_status()
    }


@bond_security_router.post("/kill-switch/reset")
async def reset_bond_kill_switch(request: KillSwitchResetRequest):
    """Reset the kill switch."""
    security = get_bond_security()
    
    if not security.is_trading_halted():
        return {"success": False, "message": "Kill switch is not active"}
    
    success = await security.reset_kill_switch(request.reset_by, request.reason)
    
    return {
        "success": success,
        "message": "Kill switch reset successfully" if success else "Failed to reset",
        "new_status": security.get_risk_status()
    }


@bond_security_router.get("/order-history")
async def get_bond_order_history(
    symbol: Optional[str] = None,
    limit: int = 50
):
    """Get bond order history from ledger."""
    security = get_bond_security()
    history = await security.get_order_history(symbol=symbol, limit=limit)
    return {"history": history, "count": len(history)}


@bond_security_router.get("/open-orders")
async def get_bond_open_orders():
    """Get open orders from ledger."""
    security = get_bond_security()
    orders = await security.get_open_orders()
    return {"orders": orders, "count": len(orders)}


@bond_security_router.get("/policies")
async def get_bond_policies():
    """Get current bond trading risk policies."""
    security = get_bond_security()
    return {
        "policies": security.risk_engine.policies.to_dict(),
        "version": security.risk_engine.policies.version
    }


@bond_security_router.get("/health")
async def bond_security_health_check():
    """Bond Security service health check."""
    security = get_bond_security()
    return {
        "status": "healthy",
        "initialized": security._initialized,
        "kill_switch_active": security.is_trading_halted(),
        "policy_version": security.risk_engine.policies.version
    }
