import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class RiskTrendService:
    """Stores and retrieves historical risk metric snapshots for trend analysis."""

    def __init__(self, db):
        self.db = db

    async def save_snapshot(self, user_id: str, risk_data: Dict[str, Any]):
        """Save a risk metric snapshot for trend tracking."""
        snapshot = {
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "var_95": risk_data.get("var", {}).get("historical_95", 0),
            "var_99": risk_data.get("var", {}).get("historical_99", 0),
            "cvar_95": risk_data.get("var", {}).get("cvar_95", 0),
            "sharpe": risk_data.get("metrics", {}).get("sharpe_ratio", 0),
            "sortino": risk_data.get("metrics", {}).get("sortino_ratio", 0),
            "max_drawdown": risk_data.get("metrics", {}).get("max_drawdown_pct", 0),
            "annual_vol": risk_data.get("metrics", {}).get("annual_volatility", 0),
            "daily_vol": risk_data.get("metrics", {}).get("daily_volatility", 0),
            "beta": risk_data.get("metrics", {}).get("beta", 0),
            "total_value": risk_data.get("metrics", {}).get("total_value", 0),
        }
        await self.db.risk_snapshots.insert_one(snapshot)
        return True

    async def get_trend_data(self, user_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get historical risk snapshots for trend visualization."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        snapshots = await self.db.risk_snapshots.find(
            {"user_id": user_id, "timestamp": {"$gte": cutoff}},
            {"_id": 0}
        ).sort("timestamp", 1).to_list(500)
        return snapshots

    async def get_latest_snapshot(self, user_id: str) -> Dict[str, Any]:
        """Get the most recent risk snapshot."""
        snap = await self.db.risk_snapshots.find_one(
            {"user_id": user_id}, {"_id": 0},
            sort=[("timestamp", -1)]
        )
        return snap or {}

    async def get_trend_summary(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get trend summary with deltas comparing current vs period start."""
        snapshots = await self.get_trend_data(user_id, days)
        if len(snapshots) < 2:
            return {"has_data": False, "snapshots_count": len(snapshots)}

        first = snapshots[0]
        last = snapshots[-1]

        def delta(key):
            return round(last.get(key, 0) - first.get(key, 0), 4)

        return {
            "has_data": True,
            "snapshots_count": len(snapshots),
            "period_days": days,
            "current": {
                "var_95": last.get("var_95", 0),
                "annual_vol": last.get("annual_vol", 0),
                "sharpe": last.get("sharpe", 0),
                "max_drawdown": last.get("max_drawdown", 0),
                "total_value": last.get("total_value", 0),
            },
            "deltas": {
                "var_95": delta("var_95"),
                "annual_vol": delta("annual_vol"),
                "sharpe": delta("sharpe"),
                "max_drawdown": delta("max_drawdown"),
                "total_value": delta("total_value"),
            },
            "first_date": first.get("timestamp", ""),
            "last_date": last.get("timestamp", ""),
        }
