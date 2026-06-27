"""
Security API Routes for Crypto Trading System
Provides REST endpoints for risk management, audit, and security features.
"""
import os
import sys
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

# Add shared_security to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared_security'))

from security_integration import get_security_integration, CryptoSecurityIntegration

security_router = APIRouter(prefix="/api/security", tags=["Security"])


class TradeIntentRequest(BaseModel):
    symbol: str
    side: str  # BUY or SELL
    desired_notional_usd: float
    portfolio_state: Optional[dict] = None
    market_state: Optional[dict] = None


class KillSwitchResetRequest(BaseModel):
    reset_by: str
    reason: str


# Global security instance - set during app initialization
_security: Optional[CryptoSecurityIntegration] = None


def set_security_instance(security: CryptoSecurityIntegration):
    """Set the global security instance."""
    global _security
    _security = security


def get_security() -> CryptoSecurityIntegration:
    """Get the security instance."""
    if _security is None:
        raise HTTPException(status_code=500, detail="Security service not initialized")
    return _security


@security_router.get("/status")
async def get_security_status():
    """Get current security/risk status."""
    security = get_security()
    status = security.get_risk_status()
    return {
        "status": "ok",
        "risk_status": status,
        "trading_halted": security.is_trading_halted(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@security_router.post("/evaluate-intent")
async def evaluate_trade_intent(request: TradeIntentRequest):
    """
    Evaluate a trading intent against risk policies.
    Returns approval status, warnings, and adjusted parameters.
    """
    security = get_security()
    
    # Default portfolio state if not provided
    portfolio_state = request.portfolio_state or {
        "daily_pnl_usd": 0,
        "gross_exposure_usd": 0,
        "consecutive_losses": 0
    }
    
    # Default market state if not provided
    market_state = request.market_state or {
        "price": 0,
        "bid": 0,
        "ask": 0,
        "regime": "NORMAL"
    }
    
    result = await security.evaluate_trade_intent(
        symbol=request.symbol,
        side=request.side,
        desired_notional_usd=request.desired_notional_usd,
        portfolio_state=portfolio_state,
        market_state=market_state
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


@security_router.get("/kill-switch")
async def get_kill_switch_status():
    """Get kill switch status."""
    security = get_security()
    return {
        "active": security.is_trading_halted(),
        "status": security.get_risk_status()
    }


@security_router.post("/kill-switch/reset")
async def reset_kill_switch(request: KillSwitchResetRequest):
    """Reset the kill switch (requires authorization)."""
    security = get_security()
    
    if not security.is_trading_halted():
        return {"success": False, "message": "Kill switch is not active"}
    
    success = await security.reset_kill_switch(request.reset_by, request.reason)
    
    return {
        "success": success,
        "message": "Kill switch reset successfully" if success else "Failed to reset kill switch",
        "new_status": security.get_risk_status()
    }


@security_router.get("/audit-history")
async def get_audit_history(
    symbol: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = 50
):
    """Get risk decision audit history."""
    security = get_security()
    history = await security.audit_service.get_audit_history(
        symbol=symbol,
        decision=decision,
        limit=limit
    )
    return {"history": history, "count": len(history)}


@security_router.get("/policies")
async def get_current_policies():
    """Get current risk policies."""
    security = get_security()
    return {
        "policies": security.risk_engine.policies.to_dict(),
        "version": security.risk_engine.policies.version
    }


@security_router.get("/health")
async def security_health_check():
    """Security service health check."""
    security = get_security()
    return {
        "status": "healthy",
        "initialized": security._initialized,
        "kill_switch_active": security.is_trading_halted(),
        "policy_version": security.risk_engine.policies.version
    }
