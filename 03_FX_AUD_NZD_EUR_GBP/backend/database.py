"""MongoDB database module for FX Trading System"""
import os
import logging
from datetime import datetime, timezone
from pymongo import MongoClient, DESCENDING

logger = logging.getLogger("fx_main")

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        _db = _client[DB_NAME]
        _ensure_indexes()
        logger.info(f"MongoDB connected: {DB_NAME}")
    return _db


def _ensure_indexes():
    db = _db
    db.settings.create_index("key", unique=True)
    db.alert_history.create_index([("timestamp", DESCENDING)])
    db.ai_analyses.create_index([("timestamp", DESCENDING)])
    db.backtest_results.create_index([("pair", 1), ("timestamp", DESCENDING)])


# ─── Settings ───────────────────────────────────────────────────────────────────

def load_settings(defaults: dict) -> dict:
    db = get_db()
    result = dict(defaults)
    for doc in db.settings.find({}, {"_id": 0}):
        result[doc["key"]] = doc["value"]
    return result


def save_setting(key: str, value: str):
    db = get_db()
    db.settings.update_one(
        {"key": key},
        {"$set": {"key": key, "value": value, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


# ─── Telegram Config ────────────────────────────────────────────────────────────

def load_telegram_config() -> dict:
    db = get_db()
    doc = db.telegram_config.find_one({"_id": "config"})
    if doc:
        return {"bot_token": doc.get("bot_token", ""), "chat_id": doc.get("chat_id", "")}
    return {"bot_token": "", "chat_id": ""}


def save_telegram_config(bot_token: str, chat_id: str):
    db = get_db()
    db.telegram_config.update_one(
        {"_id": "config"},
        {"$set": {"bot_token": bot_token, "chat_id": chat_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


# ─── Alert History ───────────────────────────────────────────────────────────────

def store_alert(alert_type: str, content: str, success: bool):
    db = get_db()
    db.alert_history.insert_one({
        "type": alert_type,
        "content": content[:500],
        "message": content[:500],
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def get_alert_history(limit: int = 50) -> list:
    db = get_db()
    return list(db.alert_history.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit))


# ─── AI Analyses ─────────────────────────────────────────────────────────────────

def store_ai_analysis(analysis: dict):
    db = get_db()
    doc = {k: v for k, v in analysis.items() if k != "_id"}
    doc["timestamp"] = doc.get("timestamp", datetime.now(timezone.utc).isoformat())
    db.ai_analyses.insert_one(doc)


def get_ai_analyses(limit: int = 20) -> list:
    db = get_db()
    return list(db.ai_analyses.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit))


# ─── Backtest Results ────────────────────────────────────────────────────────────

def store_backtest_results(results: list):
    db = get_db()
    if results:
        db.backtest_results.delete_many({})
        docs = [{k: v for k, v in r.items() if k != "_id"} for r in results]
        db.backtest_results.insert_many(docs)


def get_backtest_results(pair: str = None) -> list:
    db = get_db()
    query = {"pair": pair} if pair else {}
    return list(db.backtest_results.find(query, {"_id": 0}).sort("timestamp", DESCENDING))


def get_confirmation_stats() -> dict:
    db = get_db()
    stats = {
        "AUD/USD": {"A": {"total": 0, "success": 0}, "B": {"total": 0, "success": 0}},
        "NZD/USD": {"A": {"total": 0, "success": 0}, "B": {"total": 0, "success": 0}},
    }
    for result in db.backtest_results.find({}, {"_id": 0, "pair": 1, "event_level": 1, "confirmation_success": 1}):
        pair = result.get("pair", "")
        level = result.get("event_level", "")
        if pair in stats and level in stats.get(pair, {}):
            stats[pair][level]["total"] += 1
            if result.get("confirmation_success"):
                stats[pair][level]["success"] += 1
    return stats
