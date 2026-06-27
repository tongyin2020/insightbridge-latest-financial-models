"""
Security API Routes for FX Trading System
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

from security_integration import get_fx_security_integration, FXSecurityIntegration

fx_security_router = APIRouter(prefix="/api/security", tags=["Security"])


class FXTradeIntentRequest(BaseModel):
    pair: str  # AUD/USD or NZD/USD
    side: str  # BUY or SELL
    desired_notional_usd: float
    spread_pips: Optional[float] = 1.5
    risk_control_state: Optional[dict] = None
    market_data: Optional[dict] = None


class KillSwitchResetRequest(BaseModel):
    reset_by: str
    reason: str


# Global security instance
_fx_security: Optional[FXSecurityIntegration] = None


def set_fx_security_instance(security: FXSecurityIntegration):
    """Set the global FX security instance."""
    global _fx_security
    _fx_security = security


def get_fx_security() -> FXSecurityIntegration:
    """Get the FX security instance."""
    if _fx_security is None:
        raise HTTPException(status_code=500, detail="FX Security service not initialized")
    return _fx_security


@fx_security_router.get("/status")
async def get_fx_security_status():
    """Get current FX security/risk status."""
    security = get_fx_security()
    status = security.get_risk_status()
    return {
        "status": "ok",
        "risk_status": status,
        "trading_halted": security.is_trading_halted(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@fx_security_router.post("/evaluate-intent")
async def evaluate_fx_trade_intent(request: FXTradeIntentRequest):
    """
    Evaluate an FX trading intent against risk policies.
    """
    security = get_fx_security()
    
    risk_control_state = request.risk_control_state or {
        "daily_stats": {"total_pnl_pips": 0, "consecutive_losses": 0},
        "weekly_stats": {"total_pnl_pips": 0}
    }
    
    market_data = request.market_data or {
        "bid": 0.63,
        "ask": 0.6302,
        "spread_pips": request.spread_pips,
        "vol_ratio": 1.0,
        "regime": "NORMAL"
    }
    
    result = await security.evaluate_trade_intent(
        pair=request.pair,
        side=request.side,
        desired_notional_usd=request.desired_notional_usd,
        risk_control_state=risk_control_state,
        market_data=market_data
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


@fx_security_router.post("/check-entry")
async def check_fx_entry(request: FXTradeIntentRequest):
    """
    Check if entry is allowed with combined risk control and security checks.
    """
    security = get_fx_security()
    
    risk_control_state = request.risk_control_state or {}
    market_data = request.market_data or {"spread_pips": request.spread_pips}
    
    result = await security.check_entry_with_security(
        pair=request.pair,
        direction=request.side,
        spread_pips=request.spread_pips or 1.5,
        risk_control_state=risk_control_state,
        market_data=market_data,
        notional_usd=request.desired_notional_usd
    )
    
    return result


@fx_security_router.get("/kill-switch")
async def get_fx_kill_switch_status():
    """Get kill switch status."""
    security = get_fx_security()
    return {
        "active": security.is_trading_halted(),
        "status": security.get_risk_status()
    }


@fx_security_router.post("/kill-switch/reset")
async def reset_fx_kill_switch(request: KillSwitchResetRequest):
    """Reset the kill switch."""
    security = get_fx_security()
    
    if not security.is_trading_halted():
        return {"success": False, "message": "Kill switch is not active"}
    
    success = await security.reset_kill_switch(request.reset_by, request.reason)
    
    return {
        "success": success,
        "message": "Kill switch reset successfully" if success else "Failed to reset",
        "new_status": security.get_risk_status()
    }


@fx_security_router.get("/audit-history")
async def get_fx_audit_history(
    pair: Optional[str] = None,
    limit: int = 50
):
    """Get FX risk decision audit history."""
    security = get_fx_security()
    history = await security.get_audit_history(pair=pair, limit=limit)
    return {"history": history, "count": len(history)}


@fx_security_router.get("/policies")
async def get_fx_policies():
    """Get current FX risk policies."""
    security = get_fx_security()
    return {
        "policies": security.risk_engine.policies.to_dict(),
        "version": security.risk_engine.policies.version
    }


@fx_security_router.get("/health")
async def fx_security_health_check():
    """FX Security service health check."""
    security = get_fx_security()
    return {
        "status": "healthy",
        "initialized": security._initialized,
        "kill_switch_active": security.is_trading_halted(),
        "policy_version": security.risk_engine.policies.version
    }
