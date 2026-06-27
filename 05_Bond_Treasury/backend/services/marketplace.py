import random
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId
from fastapi import HTTPException
from models.schemas import StrategyType

logger = logging.getLogger(__name__)


class StrategyMarketplace:
    def __init__(self, db):
        self.db = db

    async def publish_strategy(self, user_id: str, user_name: str, name: str, description: str,
                              strategy_type: StrategyType, config: Dict[str, Any]) -> Dict[str, Any]:
        existing = await self.db.published_strategies.find_one({"user_id": user_id, "name": name})
        if existing:
            raise HTTPException(status_code=400, detail="You already have a strategy with this name")

        strategy_doc = {
            "id": str(ObjectId()),
            "user_id": user_id, "user_name": user_name,
            "name": name, "description": description,
            "strategy_type": strategy_type.value,
            "config": config, "is_public": True,
            "subscribers": 0, "rating": 0.0, "total_ratings": 0,
            "performance": {
                "total_return_pct": round(random.uniform(-5, 25), 2),
                "sharpe_ratio": round(random.uniform(0.5, 2.5), 2),
                "max_drawdown_pct": round(random.uniform(5, 20), 2),
                "win_rate": round(random.uniform(45, 70), 1)
            },
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        await self.db.published_strategies.insert_one(strategy_doc)
        strategy_doc.pop("_id", None)
        return strategy_doc

    async def get_marketplace_strategies(self, limit: int = 50, sort_by: str = "subscribers") -> List[Dict[str, Any]]:
        sort_field = {
            "subscribers": ("subscribers", -1),
            "rating": ("rating", -1),
            "newest": ("created_at", -1),
            "performance": ("performance.total_return_pct", -1)
        }.get(sort_by, ("subscribers", -1))
        strategies = await self.db.published_strategies.find(
            {"is_public": True}, {"_id": 0}
        ).sort(sort_field[0], sort_field[1]).limit(limit).to_list(limit)
        return strategies

    async def get_strategy_details(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        strategy = await self.db.published_strategies.find_one({"id": strategy_id}, {"_id": 0})
        if strategy:
            ratings = await self.db.strategy_ratings.find(
                {"strategy_id": strategy_id}, {"_id": 0}
            ).sort("created_at", -1).limit(10).to_list(10)
            strategy["recent_ratings"] = ratings
        return strategy

    async def subscribe_to_strategy(self, user_id: str, strategy_id: str, auto_execute: bool = False) -> Dict[str, Any]:
        strategy = await self.db.published_strategies.find_one({"id": strategy_id})
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        existing = await self.db.strategy_subscriptions.find_one({"user_id": user_id, "strategy_id": strategy_id})
        if existing:
            raise HTTPException(status_code=400, detail="Already subscribed to this strategy")
        subscription = {
            "user_id": user_id, "strategy_id": strategy_id,
            "strategy_name": strategy["name"], "creator_name": strategy["user_name"],
            "auto_execute": auto_execute,
            "subscribed_at": datetime.now(timezone.utc)
        }
        await self.db.strategy_subscriptions.insert_one(subscription)
        await self.db.published_strategies.update_one({"id": strategy_id}, {"$inc": {"subscribers": 1}})
        subscription.pop("_id", None)
        return subscription

    async def unsubscribe_from_strategy(self, user_id: str, strategy_id: str) -> Dict[str, str]:
        result = await self.db.strategy_subscriptions.delete_one({"user_id": user_id, "strategy_id": strategy_id})
        if result.deleted_count > 0:
            await self.db.published_strategies.update_one({"id": strategy_id}, {"$inc": {"subscribers": -1}})
            return {"message": "Unsubscribed successfully"}
        raise HTTPException(status_code=404, detail="Subscription not found")

    async def get_user_subscriptions(self, user_id: str) -> List[Dict[str, Any]]:
        subscriptions = await self.db.strategy_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(100)
        return subscriptions

    async def get_user_published_strategies(self, user_id: str) -> List[Dict[str, Any]]:
        strategies = await self.db.published_strategies.find({"user_id": user_id}, {"_id": 0}).to_list(100)
        return strategies

    async def rate_strategy(self, user_id: str, strategy_id: str, rating: int, comment: Optional[str] = None) -> Dict[str, Any]:
        if rating < 1 or rating > 5:
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
        subscription = await self.db.strategy_subscriptions.find_one({"user_id": user_id, "strategy_id": strategy_id})
        if not subscription:
            raise HTTPException(status_code=400, detail="You must subscribe to rate this strategy")
        existing_rating = await self.db.strategy_ratings.find_one({"user_id": user_id, "strategy_id": strategy_id})
        if existing_rating:
            await self.db.strategy_ratings.update_one(
                {"user_id": user_id, "strategy_id": strategy_id},
                {"$set": {"rating": rating, "comment": comment, "updated_at": datetime.now(timezone.utc)}}
            )
        else:
            await self.db.strategy_ratings.insert_one({
                "user_id": user_id, "strategy_id": strategy_id,
                "rating": rating, "comment": comment,
                "created_at": datetime.now(timezone.utc)
            })
            await self.db.published_strategies.update_one({"id": strategy_id}, {"$inc": {"total_ratings": 1}})
        all_ratings = await self.db.strategy_ratings.find({"strategy_id": strategy_id}).to_list(1000)
        avg_rating = sum(r["rating"] for r in all_ratings) / len(all_ratings) if all_ratings else 0
        await self.db.published_strategies.update_one({"id": strategy_id}, {"$set": {"rating": round(avg_rating, 2)}})
        return {"message": "Rating submitted", "new_average": round(avg_rating, 2)}

    async def delete_strategy(self, user_id: str, strategy_id: str) -> Dict[str, str]:
        result = await self.db.published_strategies.delete_one({"id": strategy_id, "user_id": user_id})
        if result.deleted_count > 0:
            await self.db.strategy_subscriptions.delete_many({"strategy_id": strategy_id})
            await self.db.strategy_ratings.delete_many({"strategy_id": strategy_id})
            return {"message": "Strategy deleted successfully"}
        raise HTTPException(status_code=404, detail="Strategy not found or you don't have permission")
