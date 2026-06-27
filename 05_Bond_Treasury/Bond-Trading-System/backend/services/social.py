import io
import base64
import secrets
import logging
import pyotp
import qrcode
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId
from fastapi import HTTPException
from models.schemas import TwoFactorSetup, TradingSignal

logger = logging.getLogger(__name__)


class TwoFactorAuthService:
    def generate_secret(self) -> str:
        return pyotp.random_base32()

    def generate_backup_codes(self, count: int = 8) -> List[str]:
        return [secrets.token_hex(4).upper() for _ in range(count)]

    def get_totp_uri(self, email: str, secret: str) -> str:
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name="AI Bond Trading")

    def generate_qr_code(self, uri: str) -> str:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return base64.b64encode(buffer.getvalue()).decode()

    def verify_totp(self, secret: str, code: str) -> bool:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)

    async def setup_2fa(self, db, user_id: str, email: str) -> TwoFactorSetup:
        secret = self.generate_secret()
        backup_codes = self.generate_backup_codes()
        uri = self.get_totp_uri(email, secret)
        qr_code = self.generate_qr_code(uri)
        await db.pending_2fa.update_one(
            {"user_id": user_id},
            {"$set": {"secret": secret, "backup_codes": backup_codes, "created_at": datetime.now(timezone.utc)}},
            upsert=True
        )
        return TwoFactorSetup(
            secret=secret,
            qr_code=f"data:image/png;base64,{qr_code}",
            backup_codes=backup_codes
        )

    async def confirm_2fa(self, db, user_id: str, code: str) -> bool:
        pending = await db.pending_2fa.find_one({"user_id": user_id})
        if not pending:
            raise HTTPException(status_code=400, detail="No pending 2FA setup")
        if not self.verify_totp(pending["secret"], code):
            raise HTTPException(status_code=400, detail="Invalid verification code")
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"two_factor_enabled": True, "two_factor_secret": pending["secret"],
                      "two_factor_backup_codes": pending["backup_codes"]}}
        )
        await db.pending_2fa.delete_one({"user_id": user_id})
        return True

    async def disable_2fa(self, db, user_id: str, code: str) -> bool:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user or not user.get("two_factor_enabled"):
            raise HTTPException(status_code=400, detail="2FA not enabled")
        if not self.verify_totp(user["two_factor_secret"], code):
            raise HTTPException(status_code=400, detail="Invalid verification code")
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$unset": {"two_factor_enabled": "", "two_factor_secret": "", "two_factor_backup_codes": ""}}
        )
        return True

    async def verify_login_2fa(self, db, user_id: str, code: str) -> bool:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            return False
        if self.verify_totp(user.get("two_factor_secret", ""), code):
            return True
        backup_codes = user.get("two_factor_backup_codes", [])
        if code.upper() in backup_codes:
            backup_codes.remove(code.upper())
            await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"two_factor_backup_codes": backup_codes}}
            )
            return True
        return False


class SocialService:
    def __init__(self, db):
        self.db = db

    async def follow_user(self, follower_id: str, following_id: str) -> Dict[str, str]:
        if follower_id == following_id:
            raise HTTPException(status_code=400, detail="Cannot follow yourself")
        existing = await self.db.user_follows.find_one({"follower_id": follower_id, "following_id": following_id})
        if existing:
            raise HTTPException(status_code=400, detail="Already following this user")
        target_user = await self.db.users.find_one({"_id": ObjectId(following_id)})
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        await self.db.user_follows.insert_one({
            "follower_id": follower_id, "following_id": following_id,
            "followed_at": datetime.now(timezone.utc)
        })
        return {"message": f"Now following {target_user.get('name', 'user')}"}

    async def unfollow_user(self, follower_id: str, following_id: str) -> Dict[str, str]:
        result = await self.db.user_follows.delete_one({"follower_id": follower_id, "following_id": following_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Not following this user")
        return {"message": "Unfollowed successfully"}

    async def get_followers(self, user_id: str) -> List[Dict[str, Any]]:
        follows = await self.db.user_follows.find({"following_id": user_id}).to_list(1000)
        followers = []
        for follow in follows:
            user = await self.db.users.find_one({"_id": ObjectId(follow["follower_id"])})
            if user:
                followers.append({
                    "user_id": str(user["_id"]), "name": user.get("name", "Unknown"),
                    "email": user.get("email", ""), "followed_at": follow["followed_at"].isoformat()
                })
        return followers

    async def get_following(self, user_id: str) -> List[Dict[str, Any]]:
        follows = await self.db.user_follows.find({"follower_id": user_id}).to_list(1000)
        following = []
        for follow in follows:
            user = await self.db.users.find_one({"_id": ObjectId(follow["following_id"])})
            if user:
                following.append({
                    "user_id": str(user["_id"]), "name": user.get("name", "Unknown"),
                    "email": user.get("email", ""), "followed_at": follow["followed_at"].isoformat()
                })
        return following

    async def create_activity(self, user_id: str, user_name: str, activity_type: str,
                             description: str, metadata: Dict[str, Any] = None):
        await self.db.activities.insert_one({
            "id": str(ObjectId()), "user_id": user_id, "user_name": user_name,
            "activity_type": activity_type, "description": description,
            "metadata": metadata or {}, "created_at": datetime.now(timezone.utc)
        })

    async def get_activity_feed(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        follows = await self.db.user_follows.find({"follower_id": user_id}).to_list(1000)
        following_ids = [f["following_id"] for f in follows]
        following_ids.append(user_id)
        activities = await self.db.activities.find(
            {"user_id": {"$in": following_ids}}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        return activities

    async def get_global_activity(self, limit: int = 50) -> List[Dict[str, Any]]:
        activities = await self.db.activities.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
        return activities

    async def get_leaderboard(self, limit: int = 20) -> List[Dict[str, Any]]:
        users = await self.db.users.find({}, {"_id": 1, "name": 1, "email": 1}).to_list(1000)
        leaderboard = []
        for user in users:
            user_id = str(user["_id"])
            trades = await self.db.trades.find({"user_id": user_id}).to_list(1000)
            paper_trades = await self.db.paper_trades.find({"user_id": user_id}).to_list(1000)
            all_trades = trades + paper_trades
            total_trades = len(all_trades)
            if total_trades == 0:
                continue
            total_pnl = sum(t.get("pnl", 0) for t in trades if "pnl" in t)
            profitable = len([t for t in trades if t.get("pnl", 0) > 0])
            win_rate = (profitable / len(trades) * 100) if trades else 0
            followers = await self.db.user_follows.count_documents({"following_id": user_id})
            following = await self.db.user_follows.count_documents({"follower_id": user_id})
            strategies = await self.db.published_strategies.count_documents({"user_id": user_id})
            leaderboard.append({
                "user_id": user_id, "user_name": user.get("name", "Unknown"),
                "total_trades": total_trades, "profitable_trades": profitable,
                "total_pnl": round(total_pnl, 2), "win_rate": round(win_rate, 1),
                "followers": followers, "following": following, "strategies_published": strategies
            })
        leaderboard.sort(key=lambda x: x["total_pnl"], reverse=True)
        for i, trader in enumerate(leaderboard[:limit], 1):
            trader["rank"] = i
        return leaderboard[:limit]

    async def get_trader_profile(self, user_id: str, current_user_id: str = None) -> Dict[str, Any]:
        user = await self.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        trades = await self.db.trades.find({"user_id": user_id}).to_list(1000)
        paper_trades = await self.db.paper_trades.find({"user_id": user_id}).to_list(1000)
        total_pnl = sum(t.get("pnl", 0) for t in trades if "pnl" in t)
        profitable = len([t for t in trades if t.get("pnl", 0) > 0])
        win_rate = (profitable / len(trades) * 100) if trades else 0
        followers = await self.db.user_follows.count_documents({"following_id": user_id})
        following = await self.db.user_follows.count_documents({"follower_id": user_id})
        strategies = await self.db.published_strategies.count_documents({"user_id": user_id})
        is_following = False
        if current_user_id:
            follow = await self.db.user_follows.find_one({"follower_id": current_user_id, "following_id": user_id})
            is_following = follow is not None
        activities = await self.db.activities.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("created_at", -1).limit(10).to_list(10)
        return {
            "user_id": user_id, "name": user.get("name", "Unknown"),
            "email": user.get("email", ""), "role": user.get("role", "user"),
            "created_at": user.get("created_at", datetime.now(timezone.utc)).isoformat(),
            "total_trades": len(trades), "paper_trades": len(paper_trades),
            "total_pnl": round(total_pnl, 2), "win_rate": round(win_rate, 1),
            "followers": followers, "following": following, "strategies_published": strategies,
            "is_following": is_following, "recent_activities": activities
        }


class AutoExecuteService:
    def __init__(self, db, paper_trading_manager, social_service):
        self.db = db
        self.paper_trading_manager = paper_trading_manager
        self.social_service = social_service

    async def process_strategy_signal(self, strategy_id: str, signal: TradingSignal):
        strategy = await self.db.published_strategies.find_one({"id": strategy_id})
        if not strategy:
            return
        subscriptions = await self.db.strategy_subscriptions.find({
            "strategy_id": strategy_id, "auto_execute": True
        }).to_list(1000)
        for sub in subscriptions:
            user_id = sub["user_id"]
            try:
                asset = "10Y_BOND" if "BOND" in signal.signal_type.value else "WTI"
                action = "BUY" if "BUY" in signal.signal_type.value or "LONG" in signal.signal_type.value else "SELL"
                quantity = strategy.get("config", {}).get("max_position_size", 10)
                await self.paper_trading_manager.execute_paper_trade(user_id, asset, quantity, action)
                await self.db.auto_execute_logs.insert_one({
                    "id": str(ObjectId()), "user_id": user_id, "strategy_id": strategy_id,
                    "strategy_name": strategy["name"], "signal_type": signal.signal_type.value,
                    "execution_price": signal.execution_price or 0, "quantity": quantity,
                    "status": "EXECUTED", "created_at": datetime.now(timezone.utc)
                })
                user = await self.db.users.find_one({"_id": ObjectId(user_id)})
                if user:
                    await self.social_service.create_activity(
                        user_id, user.get("name", "Unknown"), "AUTO_TRADE",
                        f"Auto-executed {action} {quantity} {asset} from strategy '{strategy['name']}'",
                        {"strategy_id": strategy_id, "signal_type": signal.signal_type.value}
                    )
                logger.info(f"Auto-executed trade for user {user_id} from strategy {strategy_id}")
            except Exception as e:
                await self.db.auto_execute_logs.insert_one({
                    "id": str(ObjectId()), "user_id": user_id, "strategy_id": strategy_id,
                    "strategy_name": strategy["name"], "signal_type": signal.signal_type.value,
                    "execution_price": signal.execution_price or 0, "quantity": 0,
                    "status": "FAILED", "error_message": str(e), "created_at": datetime.now(timezone.utc)
                })
                logger.error(f"Auto-execute failed for user {user_id}: {e}")

    async def get_auto_execute_logs(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        logs = await self.db.auto_execute_logs.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        return logs
