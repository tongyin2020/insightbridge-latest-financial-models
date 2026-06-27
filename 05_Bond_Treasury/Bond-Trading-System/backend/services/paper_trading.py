import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from bson import ObjectId
from models.schemas import AVAILABLE_ASSETS

logger = logging.getLogger(__name__)


class PaperTradingManager:
    def __init__(self, db, multi_asset_service):
        self.db = db
        self.multi_asset_service = multi_asset_service

    async def get_paper_portfolio(self, user_id: str) -> Dict[str, Any]:
        portfolio = await self.db.paper_portfolios.find_one({"user_id": user_id})
        if not portfolio:
            portfolio = {
                "user_id": user_id,
                "cash": 100000.0,
                "positions": {},
                "total_value": 100000.0,
                "total_pnl": 0.0,
                "initial_capital": 100000.0,
                "created_at": datetime.now(timezone.utc)
            }
            await self.db.paper_portfolios.insert_one(portfolio)

        # Update current prices - handle both dict and list formats for positions
        positions_with_prices = {}
        raw_positions = portfolio.get("positions", {})
        
        # Convert list format to dict format if needed
        if isinstance(raw_positions, list):
            positions_dict = {}
            for pos in raw_positions:
                symbol_key = pos.get("asset") or pos.get("symbol")
                if symbol_key:
                    positions_dict[symbol_key] = {
                        "quantity": pos.get("quantity", 0),
                        "avg_price": pos.get("avg_price", 0)
                    }
            raw_positions = positions_dict
        
        for symbol, pos in raw_positions.items():
            price_data = await self.multi_asset_service.get_asset_price(symbol)
            current_price = price_data["price"] if price_data else pos.get("avg_price", 0)
            qty = pos["quantity"]
            avg_price = pos["avg_price"]
            market_value = qty * current_price
            unrealized_pnl = (current_price - avg_price) * qty
            positions_with_prices[symbol] = {
                "symbol": symbol,
                "name": AVAILABLE_ASSETS.get(symbol, type('', (), {'name': symbol})).name,
                "quantity": qty,
                "avg_price": round(avg_price, 4),
                "current_price": round(current_price, 4),
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round((unrealized_pnl / (avg_price * qty) * 100) if avg_price * qty > 0 else 0, 2)
            }

        positions_value = sum(p["market_value"] for p in positions_with_prices.values())
        cash = portfolio.get("cash", 100000.0)
        total_value = cash + positions_value
        initial = portfolio.get("initial_capital", 100000.0)

        return {
            "cash": round(cash, 2),
            "positions": positions_with_prices,
            "total_value": round(total_value, 2),
            "total_pnl": round(total_value - initial, 2),
            "total_pnl_pct": round((total_value - initial) / initial * 100, 2) if initial > 0 else 0,
            "initial_capital": initial
        }

    async def execute_paper_trade(self, user_id: str, symbol: str, quantity: int, action: str) -> Dict[str, Any]:
        from fastapi import HTTPException

        if symbol not in AVAILABLE_ASSETS:
            raise HTTPException(status_code=400, detail=f"Asset {symbol} not available for trading")

        price_data = await self.multi_asset_service.get_asset_price(symbol)
        if not price_data:
            raise HTTPException(status_code=500, detail="Could not fetch asset price")

        current_price = price_data["price"]
        portfolio = await self.db.paper_portfolios.find_one({"user_id": user_id})
        if not portfolio:
            portfolio = {
                "user_id": user_id,
                "cash": 100000.0,
                "positions": {},
                "total_value": 100000.0,
                "initial_capital": 100000.0,
                "created_at": datetime.now(timezone.utc)
            }
            await self.db.paper_portfolios.insert_one(portfolio)

        cash = portfolio.get("cash", 100000.0)
        positions = portfolio.get("positions", {})
        trade_value = quantity * current_price

        if action == "BUY":
            if cash < trade_value:
                raise HTTPException(status_code=400, detail="Insufficient paper trading funds")
            cash -= trade_value
            if symbol in positions:
                pos = positions[symbol]
                total_qty = pos["quantity"] + quantity
                avg_price = (pos["avg_price"] * pos["quantity"] + current_price * quantity) / total_qty
                positions[symbol] = {"quantity": total_qty, "avg_price": round(avg_price, 4)}
            else:
                positions[symbol] = {"quantity": quantity, "avg_price": round(current_price, 4)}
        elif action == "SELL":
            if symbol not in positions or positions[symbol]["quantity"] < quantity:
                raise HTTPException(status_code=400, detail="Insufficient position to sell")
            cash += trade_value
            pnl = (current_price - positions[symbol]["avg_price"]) * quantity
            positions[symbol]["quantity"] -= quantity
            if positions[symbol]["quantity"] == 0:
                del positions[symbol]
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use BUY or SELL")

        await self.db.paper_portfolios.update_one(
            {"user_id": user_id},
            {"$set": {"cash": round(cash, 2), "positions": positions, "updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )

        # Record trade
        trade_record = {
            "user_id": user_id,
            "symbol": symbol,
            "asset_name": AVAILABLE_ASSETS[symbol].name,
            "action": action,
            "quantity": quantity,
            "price": round(current_price, 4),
            "total_value": round(trade_value, 2),
            "timestamp": datetime.now(timezone.utc)
        }
        await self.db.paper_trades.insert_one(trade_record)

        return {
            "message": f"Paper trade executed: {action} {quantity} {symbol} @ {current_price:.4f}",
            "trade": {
                "symbol": symbol, "action": action,
                "quantity": quantity, "price": round(current_price, 4),
                "total_value": round(trade_value, 2)
            }
        }

    async def reset_paper_portfolio(self, user_id: str, initial_capital: float = 100000.0) -> Dict[str, Any]:
        await self.db.paper_portfolios.update_one(
            {"user_id": user_id},
            {"$set": {
                "cash": initial_capital,
                "positions": {},
                "total_value": initial_capital,
                "initial_capital": initial_capital,
                "updated_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        return {"message": "Paper portfolio reset", "initial_capital": initial_capital}

    async def get_paper_trade_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        trades = await self.db.paper_trades.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return trades
