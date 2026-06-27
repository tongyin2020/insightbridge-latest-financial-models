"""
WTI Trading Platform - Push Notification Service
Uses in-app notification system with SSE (Server-Sent Events) fallback
Stores notifications in MongoDB for persistence
"""
import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    TRADE_ALERT = "trade_alert"
    REGIME_CHANGE = "regime_change"
    RISK_WARNING = "risk_warning"
    STRATEGY_SIGNAL = "strategy_signal"
    PRICE_ALERT = "price_alert"
    SYSTEM = "system"


@dataclass
class Notification:
    id: str
    type: NotificationType
    title: str
    message: str
    severity: str = "info"  # info, warning, critical
    timestamp: str = ""
    read: bool = False
    data: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type.value if isinstance(self.type, NotificationType) else self.type,
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "read": self.read,
            "data": self.data,
        }


class NotificationService:
    """In-app notification service with MongoDB persistence and WebSocket push"""

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._notification_counter = 0
        self._db = None

    def set_db(self, db):
        self._db = db

    def _generate_id(self) -> str:
        self._notification_counter += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"notif_{ts}_{self._notification_counter}"

    async def send_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        severity: str = "info",
        data: Optional[Dict] = None,
    ) -> Notification:
        """Send a notification to a user"""
        notif = Notification(
            id=self._generate_id(),
            type=notification_type,
            title=title,
            message=message,
            severity=severity,
            data=data or {},
        )

        # Store in MongoDB
        if self._db is not None:
            await self._db.notifications.insert_one({
                **notif.to_dict(),
                "user_id": user_id,
            })

        # Push to live subscribers via queues
        if user_id in self._subscribers:
            for queue in self._subscribers[user_id]:
                try:
                    queue.put_nowait(notif.to_dict())
                except asyncio.QueueFull:
                    pass

        logger.info(f"[Notification] Sent to {user_id}: {title}")
        return notif

    async def broadcast_notification(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        severity: str = "info",
        data: Optional[Dict] = None,
    ):
        """Broadcast notification to all subscribers"""
        notif = Notification(
            id=self._generate_id(),
            type=notification_type,
            title=title,
            message=message,
            severity=severity,
            data=data or {},
        )

        if self._db is not None:
            await self._db.notifications.insert_one({
                **notif.to_dict(),
                "user_id": "__broadcast__",
            })

        for user_id, queues in self._subscribers.items():
            for queue in queues:
                try:
                    queue.put_nowait(notif.to_dict())
                except asyncio.QueueFull:
                    pass

        logger.info(f"[Notification] Broadcast: {title}")

    def subscribe(self, user_id: str) -> asyncio.Queue:
        """Subscribe to notifications (returns a queue to listen on)"""
        if user_id not in self._subscribers:
            self._subscribers[user_id] = []
        queue = asyncio.Queue(maxsize=50)
        self._subscribers[user_id].append(queue)
        return queue

    def unsubscribe(self, user_id: str, queue: asyncio.Queue):
        """Unsubscribe from notifications"""
        if user_id in self._subscribers:
            if queue in self._subscribers[user_id]:
                self._subscribers[user_id].remove(queue)
            if not self._subscribers[user_id]:
                del self._subscribers[user_id]

    async def get_notifications(
        self, user_id: str, limit: int = 50, unread_only: bool = False
    ) -> List[Dict]:
        """Get stored notifications for a user"""
        if self._db is None:
            return []

        query = {
            "$or": [
                {"user_id": user_id},
                {"user_id": "__broadcast__"},
            ]
        }
        if unread_only:
            query["read"] = False

        notifications = await self._db.notifications.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return notifications

    async def mark_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read"""
        if self._db is None:
            return False
        result = await self._db.notifications.update_one(
            {"id": notification_id, "$or": [{"user_id": user_id}, {"user_id": "__broadcast__"}]},
            {"$set": {"read": True}},
        )
        return result.modified_count > 0

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user"""
        if self._db is None:
            return 0
        result = await self._db.notifications.update_many(
            {"$or": [{"user_id": user_id}, {"user_id": "__broadcast__"}], "read": False},
            {"$set": {"read": True}},
        )
        return result.modified_count

    async def get_unread_count(self, user_id: str) -> int:
        """Get unread notification count"""
        if self._db is None:
            return 0
        count = await self._db.notifications.count_documents({
            "$or": [{"user_id": user_id}, {"user_id": "__broadcast__"}],
            "read": False,
        })
        return count


# Global instance
notification_service = NotificationService()
