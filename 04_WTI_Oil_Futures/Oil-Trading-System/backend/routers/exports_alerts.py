"""Trade export and price alert routes."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
import io
import csv

from deps import db, broker, notification_service, multi_asset_generator, get_optional_user
from notification_service import NotificationType
from multi_asset import ASSETS

router = APIRouter()


# ─── Trade Export (CSV) ───

@router.get("/trades/export/csv")
async def export_trades_csv(request: Request):
    """Export all trades as a CSV download."""
    user = await get_optional_user(request)
    # Gather trades from broker
    records = list(reversed(broker.trade_records))
    # Also try from DB if user is logged in
    if user:
        db_trades = await db.trades.find({"user_id": user["_id"]}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
        if db_trades:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Date", "Symbol", "Direction", "Entry Price", "Exit Price", "Quantity", "PnL ($)", "Hold (min)", "Exit Reason"])
            for t in db_trades:
                writer.writerow([
                    t.get("date", ""), t.get("symbol", ""), t.get("direction", ""),
                    t.get("entry_price", ""), t.get("exit_price", ""),
                    t.get("quantity", ""), t.get("pnl", t.get("pnl_usd", "")),
                    t.get("hold_minutes", ""), t.get("exit_reason", ""),
                ])
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=trades_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"},
            )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Symbol", "Direction", "Entry Price", "Exit Price", "Quantity", "PnL ($)", "Hold (min)", "Exit Reason"])
    for r in records:
        writer.writerow([r.date, r.symbol, r.direction, r.entry_price, r.exit_price, r.quantity, r.pnl_usd, r.hold_minutes, r.exit_reason])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=trades_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"},
    )


# ─── Price Alerts ───

@router.get("/alerts")
async def get_price_alerts(request: Request):
    """Get all active price alerts for the user."""
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    alerts = await db.price_alerts.find(
        {"user_id": user_id, "active": True}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"alerts": alerts}


@router.post("/alerts")
async def create_price_alert(request: Request):
    """Create a new price alert."""
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    body = await request.json()
    symbol = body.get("symbol", "CL")
    target_price = body.get("target_price")
    condition = body.get("condition", "above")  # "above" or "below"
    note = body.get("note", "")

    if symbol not in ASSETS:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    if target_price is None:
        raise HTTPException(status_code=400, detail="target_price is required")
    if condition not in ("above", "below"):
        raise HTTPException(status_code=400, detail="condition must be 'above' or 'below'")

    alert_id = f"alert_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{symbol}"
    doc = {
        "id": alert_id,
        "user_id": user_id,
        "symbol": symbol,
        "target_price": float(target_price),
        "condition": condition,
        "note": note,
        "active": True,
        "triggered": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.price_alerts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/alerts/{alert_id}")
async def delete_price_alert(alert_id: str, request: Request):
    """Deactivate a price alert."""
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    result = await db.price_alerts.update_one(
        {"id": alert_id, "user_id": user_id},
        {"$set": {"active": False}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}


async def check_price_alerts():
    """Called from background loop to check and trigger alerts."""
    active_alerts = await db.price_alerts.find({"active": True, "triggered": False}).to_list(100)
    for alert in active_alerts:
        symbol = alert.get("symbol", "CL")
        target = alert.get("target_price", 0)
        condition = alert.get("condition", "above")
        current_price = multi_asset_generator.current_prices.get(symbol, 0)
        triggered = False
        if condition == "above" and current_price >= target:
            triggered = True
        elif condition == "below" and current_price <= target:
            triggered = True

        if triggered:
            await db.price_alerts.update_one(
                {"id": alert["id"]},
                {"$set": {"triggered": True, "triggered_at": datetime.now(timezone.utc).isoformat(), "triggered_price": current_price}}
            )
            await notification_service.broadcast_notification(
                notification_type=NotificationType.TRADE_ALERT,
                title=f"Price Alert: {symbol} {'above' if condition == 'above' else 'below'} ${target:.2f}",
                message=f"{symbol} reached ${current_price:.2f} (target: ${target:.2f}). {alert.get('note', '')}",
                severity="warning",
            )
