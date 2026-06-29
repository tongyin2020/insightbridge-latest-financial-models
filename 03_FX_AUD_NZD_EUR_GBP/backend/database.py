"""Database module for FX Trading System.

This backend prefers MongoDB when configured, but can fall back to a lightweight
in-memory store so local bridge services can still run without a Mongo daemon or
extra Python drivers.
"""
import os
import logging
from copy import deepcopy
from datetime import datetime, timezone

try:
    from pymongo import MongoClient, DESCENDING
except Exception:  # pragma: no cover - local fallback path
    MongoClient = None
    DESCENDING = -1

logger = logging.getLogger("fx_main")

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

_client = None
_db = None


class _InMemoryCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction):
        reverse = direction == DESCENDING or direction == -1
        self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
        return self

    def limit(self, count):
        self._docs = self._docs[:count]
        return self

    def __iter__(self):
        return iter(deepcopy(self._docs))


class _InMemoryCollection:
    def __init__(self):
        self._docs = []

    def create_index(self, *args, **kwargs):
        return None

    def _match(self, doc, query):
        return all(doc.get(k) == v for k, v in (query or {}).items())

    def find(self, query=None, projection=None):
        results = [deepcopy(doc) for doc in self._docs if self._match(doc, query or {})]
        if projection:
            trimmed = []
            exclude_id = projection.get("_id") == 0
            include_keys = {k for k, v in projection.items() if v and k != "_id"}
            for doc in results:
                if include_keys:
                    new_doc = {k: doc.get(k) for k in include_keys if k in doc}
                else:
                    new_doc = dict(doc)
                if exclude_id:
                    new_doc.pop("_id", None)
                trimmed.append(new_doc)
            results = trimmed
        return _InMemoryCursor(results)

    def find_one(self, query=None, projection=None):
        for doc in self.find(query, projection):
            return doc
        return None

    def update_one(self, query, update, upsert=False):
        for idx, doc in enumerate(self._docs):
            if self._match(doc, query):
                if "$set" in update:
                    self._docs[idx] = {**doc, **update["$set"]}
                return
        if upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            self._docs.append(new_doc)

    def insert_one(self, doc):
        self._docs.append(deepcopy(doc))

    def insert_many(self, docs):
        self._docs.extend(deepcopy(list(docs)))

    def delete_many(self, query=None):
        if not query:
            self._docs = []
            return
        self._docs = [doc for doc in self._docs if not self._match(doc, query)]


class _InMemoryDB:
    def __init__(self):
        self.settings = _InMemoryCollection()
        self.telegram_config = _InMemoryCollection()
        self.alert_history = _InMemoryCollection()
        self.ai_analyses = _InMemoryCollection()
        self.backtest_results = _InMemoryCollection()
        self.users = _InMemoryCollection()


def get_db():
    global _client, _db
    if _db is None:
        if MongoClient is None or not MONGO_URL or not DB_NAME:
            _db = _InMemoryDB()
            logger.warning("MongoDB not configured; using in-memory fallback store.")
        else:
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
