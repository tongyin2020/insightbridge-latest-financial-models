"""Trading bot routes."""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional

from deps import (
    trading_bot, broker, multi_asset_generator, risk_control,
    take_profit_levels, notification_service, get_optional_user
)
from trading_bot import OpportunityStatus
from notification_service import NotificationType
from models import Direction, Signal

router = APIRouter()


@router.get("/bot/status")
async def get_bot_status():
    return trading_bot.get_status()

@router.post("/bot/toggle")
async def toggle_bot(enabled: Optional[bool] = None):
    new_state = trading_bot.toggle(enabled)
    return {"enabled": new_state}

@router.post("/bot/config")
async def update_bot_config(request: Request):
    data = await request.json()
    trading_bot.update_config(data)
    return trading_bot.get_status()

@router.get("/bot/opportunities")
async def get_pending_opportunities():
    return {"opportunities": trading_bot.get_pending_opportunities()}

@router.get("/bot/history")
async def get_bot_history(limit: int = 20):
    return {"history": trading_bot.get_history(limit)}

@router.post("/bot/approve/{opportunity_id}")
async def approve_opportunity(opportunity_id: str):
    result = trading_bot.approve_opportunity(opportunity_id)
    if not result:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    opp = trading_bot._opportunities.get(opportunity_id)
    if opp and opp.status == OpportunityStatus.APPROVED:
        direction = Direction.LONG if opp.direction.value == "long" else Direction.SHORT
        signal = Signal(
            symbol=opp.symbol, direction=direction,
            entry_price=opp.entry_price, stop_loss_price=opp.stop_loss,
            confidence=opp.confidence / 100,
        )
        tick = multi_asset_generator.generate_tick(opp.symbol)
        if tick:
            broker.update_tick(tick)
        position = broker.submit_order(signal, opp.size)
        if position:
            trading_bot.mark_executed(opportunity_id, position.id)
            risk_control.update_equity(broker.equity)
            take_profit_levels[position.id] = {
                "tp1": opp.take_profit_1, "tp2": opp.take_profit_2, "tp1_hit": False,
            }
            await notification_service.broadcast_notification(
                notification_type=NotificationType.TRADE_ALERT,
                title=f"EXECUTED: {'BUY' if direction == Direction.LONG else 'SELL'} {opp.symbol}",
                message=f"{opp.size} contracts @ ${position.entry_price:.2f} | SL: ${opp.stop_loss:.2f}",
                severity="info",
            )
            return {
                "status": "executed", "opportunity": opp.to_dict(),
                "position_id": position.id, "fill_price": position.entry_price,
            }
        else:
            return {"status": "failed", "error": "Broker could not fill order"}
    return result

@router.post("/bot/reject/{opportunity_id}")
async def reject_opportunity(opportunity_id: str):
    result = trading_bot.reject_opportunity(opportunity_id)
    if not result:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
