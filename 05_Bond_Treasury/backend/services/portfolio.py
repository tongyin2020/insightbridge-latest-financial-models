import logging
from datetime import datetime, timezone
from typing import Dict, Any
from bson import ObjectId
from models.schemas import Portfolio, PortfolioPosition

logger = logging.getLogger(__name__)


class PortfolioManager:
    def __init__(self, db):
        self.db = db

    async def get_portfolio(self, user_id: str) -> Portfolio:
        portfolio = await self.db.portfolios.find_one({"user_id": user_id})
        if not portfolio:
            portfolio = {
                "user_id": user_id,
                "cash": 100000.0,
                "positions": [],
                "total_value": 100000.0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "updated_at": datetime.now(timezone.utc)
            }
            await self.db.portfolios.insert_one(portfolio)

        positions = []
        for pos in portfolio.get("positions", []):
            positions.append(PortfolioPosition(**pos))

        return Portfolio(
            user_id=user_id,
            cash=portfolio.get("cash", 100000.0),
            positions=positions,
            total_value=portfolio.get("total_value", 100000.0),
            total_pnl=portfolio.get("total_pnl", 0.0),
            total_pnl_pct=portfolio.get("total_pnl_pct", 0.0),
            updated_at=portfolio.get("updated_at", datetime.now(timezone.utc))
        )

    async def update_position(self, user_id: str, asset: str, quantity: int, price: float, action: str) -> Portfolio:
        portfolio = await self.db.portfolios.find_one({"user_id": user_id})
        if not portfolio:
            portfolio = {
                "user_id": user_id,
                "cash": 100000.0,
                "positions": [],
                "total_value": 100000.0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "updated_at": datetime.now(timezone.utc)
            }
            await self.db.portfolios.insert_one(portfolio)

        positions = portfolio.get("positions", [])
        cash = portfolio.get("cash", 100000.0)
        trade_value = quantity * price

        if action.upper() == "BUY":
            if cash < trade_value:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Insufficient funds")
            cash -= trade_value
            existing = next((p for p in positions if p["asset"] == asset), None)
            if existing:
                total_qty = existing["quantity"] + quantity
                avg_price = (existing["avg_price"] * existing["quantity"] + price * quantity) / total_qty
                existing["quantity"] = total_qty
                existing["avg_price"] = round(avg_price, 4)
                existing["current_price"] = price
                existing["market_value"] = round(total_qty * price, 2)
                existing["unrealized_pnl"] = round((price - avg_price) * total_qty, 2)
                existing["unrealized_pnl_pct"] = round((price - avg_price) / avg_price * 100, 2) if avg_price > 0 else 0
            else:
                positions.append({
                    "asset": asset, "quantity": quantity,
                    "avg_price": round(price, 4), "current_price": price,
                    "market_value": round(quantity * price, 2),
                    "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0
                })
        elif action.upper() == "SELL":
            existing = next((p for p in positions if p["asset"] == asset), None)
            if not existing or existing["quantity"] < quantity:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Insufficient position")
            cash += trade_value
            existing["quantity"] -= quantity
            if existing["quantity"] == 0:
                positions.remove(existing)
            else:
                existing["market_value"] = round(existing["quantity"] * price, 2)
                existing["unrealized_pnl"] = round((price - existing["avg_price"]) * existing["quantity"], 2)

        total_value = cash + sum(p.get("market_value", 0) for p in positions)
        initial = 100000.0
        total_pnl = total_value - initial
        total_pnl_pct = (total_pnl / initial * 100) if initial > 0 else 0

        await self.db.portfolios.update_one(
            {"user_id": user_id},
            {"$set": {
                "cash": round(cash, 2), "positions": positions,
                "total_value": round(total_value, 2),
                "total_pnl": round(total_pnl, 2),
                "total_pnl_pct": round(total_pnl_pct, 2),
                "updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )

        return await self.get_portfolio(user_id)
