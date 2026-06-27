"""
Security API Routes for WTI Oil Trading Platform
Provides REST endpoints for risk management, audit, and security features.
"""
import os
import sys
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Add shared_security to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared_security'))

from security_integration import get_oil_security_integration, OilSecurityIntegration

oil_security_router = APIRouter(prefix="/api/security", tags=["Security"])


class OilTradeOpportunityRequest(BaseModel):
    symbol: str = "CL"
    direction: str  # long or short
    entry_price: float
    quantity: float
    confidence: float = 70.0
    risk_state: Optional[dict] = None
    market_indicators: Optional[dict] = None
    fragility_state: Optional[dict] = None


class OilBotTradeRequest(BaseModel):
    symbol: str = "CL"
    direction: str
    entry_price: float
    signal_score: dict
    execution_gate: dict
    fragility: dict
    risk_control: dict
    regime: str = "NORMAL"
    atr: float = 1.5


class OilTradeExecutionRequest(BaseModel):
    trade_id: str
    symbol: str
    direction: str
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit_levels: Optional[dict] = None


class KillSwitchResetRequest(BaseModel):
    reset_by: str
    reason: str


# Global security instance
_oil_security: Optional[OilSecurityIntegration] = None


def set_oil_security_instance(security: OilSecurityIntegration):
    """Set the global Oil security instance."""
    global _oil_security
    _oil_security = security


def get_oil_security() -> OilSecurityIntegration:
    """Get the Oil security instance."""
    if _oil_security is None:
        raise HTTPException(status_code=500, detail="Oil Security service not initialized")
    return _oil_security


@oil_security_router.get("/status")
async def get_oil_security_status():
    """Get current oil trading security/risk status."""
    security = get_oil_security()
    status = security.get_risk_status()
    return {
        "status": "ok",
        "risk_status": status,
        "trading_halted": security.is_trading_halted(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@oil_security_router.post("/evaluate-opportunity")
async def evaluate_oil_trade_opportunity(request: OilTradeOpportunityRequest):
    """
    Evaluate an oil trading opportunity against risk policies.
    """
    security = get_oil_security()
    
    risk_state = request.risk_state or {
        "daily_pnl": 0,
        "equity": 100000,
        "consecutive_losses": 0
    }
    
    market_indicators = request.market_indicators or {
        "spread": 0.03,
        "volatility_ratio": 1.0,
        "regime": "NORMAL"
    }
    
    fragility_state = request.fragility_state or {"score": 30}
    
    result = await security.evaluate_trade_opportunity(
        symbol=request.symbol,
        direction=request.direction,
        entry_price=request.entry_price,
        quantity=request.quantity,
        confidence=request.confidence,
        risk_state=risk_state,
        market_indicators=market_indicators,
        fragility_state=fragility_state
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


@oil_security_router.post("/validate-bot-trade")
async def validate_oil_bot_trade(request: OilBotTradeRequest):
    """
    Validate an automated bot trade with security layer.
    Combines execution gate and security checks.
    """
    security = get_oil_security()
    
    result = await security.validate_bot_trade(
        symbol=request.symbol,
        direction=request.direction,
        entry_price=request.entry_price,
        signal_score=request.signal_score,
        execution_gate=request.execution_gate,
        fragility=request.fragility,
        risk_control=request.risk_control,
        regime=request.regime,
        atr=request.atr
    )
    
    return result


@oil_security_router.post("/record-execution")
async def record_oil_trade_execution(request: OilTradeExecutionRequest):
    """
    Record a trade execution to the ledger with idempotency.
    """
    security = get_oil_security()
    
    result = await security.record_trade_execution(
        trade_id=request.trade_id,
        symbol=request.symbol,
        direction=request.direction,
        quantity=request.quantity,
        entry_price=request.entry_price,
        stop_loss=request.stop_loss,
        take_profit_levels=request.take_profit_levels or {}
    )
    
    return result


@oil_security_router.get("/kill-switch")
async def get_oil_kill_switch_status():
    """Get kill switch status."""
    security = get_oil_security()
    return {
        "active": security.is_trading_halted(),
        "status": security.get_risk_status()
    }


@oil_security_router.post("/kill-switch/reset")
async def reset_oil_kill_switch(request: KillSwitchResetRequest):
    """Reset the kill switch."""
    security = get_oil_security()
    
    if not security.is_trading_halted():
        return {"success": False, "message": "Kill switch is not active"}
    
    success = await security.reset_kill_switch(request.reset_by, request.reason)
    
    return {
        "success": success,
        "message": "Kill switch reset successfully" if success else "Failed to reset",
        "new_status": security.get_risk_status()
    }


@oil_security_router.get("/trade-history")
async def get_oil_trade_history(
    symbol: Optional[str] = None,
    limit: int = 50
):
    """Get oil trade history from ledger."""
    security = get_oil_security()
    history = await security.get_trade_history(symbol=symbol, limit=limit)
    return {"history": history, "count": len(history)}


@oil_security_router.get("/policies")
async def get_oil_policies():
    """Get current oil trading risk policies."""
    security = get_oil_security()
    return {
        "policies": security.risk_engine.policies.to_dict(),
        "version": security.risk_engine.policies.version
    }


@oil_security_router.get("/health")
async def oil_security_health_check():
    """Oil Security service health check."""
    security = get_oil_security()
    return {
        "status": "healthy",
        "initialized": security._initialized,
        "kill_switch_active": security.is_trading_halted(),
        "policy_version": security.risk_engine.policies.version
    }
