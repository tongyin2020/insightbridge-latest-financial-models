import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RiskAlertService:
    """Monitors portfolio risk metrics and triggers alerts when thresholds are breached."""

    def __init__(self, db, risk_analytics_service, telegram_notifier):
        self.db = db
        self.risk_analytics = risk_analytics_service
        self.telegram = telegram_notifier
        self.last_alert_time = {}

    async def get_alert_config(self, user_id: str) -> Dict[str, Any]:
        config = await self.db.risk_alert_configs.find_one({"user_id": user_id}, {"_id": 0})
        if not config:
            config = self._default_config(user_id)
        return config

    async def save_alert_config(self, user_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        config["user_id"] = user_id
        config["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.db.risk_alert_configs.update_one(
            {"user_id": user_id}, {"$set": config}, upsert=True
        )
        return {k: v for k, v in config.items() if k != "_id"}

    async def get_alert_history(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        alerts = await self.db.risk_alerts.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("triggered_at", -1).limit(limit).to_list(limit)
        return alerts

    async def check_risk_and_alert(self, user_id: str) -> Dict[str, Any]:
        """Run risk check against user thresholds and fire alerts if breached."""
        config = await self.get_alert_config(user_id)
        if not config.get("enabled", True):
            return {"checked": True, "alerts_fired": 0, "message": "Risk alerts disabled"}

        risk_data = await self.risk_analytics.compute_portfolio_risk(user_id)
        alerts_fired = []

        # 1. VaR threshold check
        var_threshold = config.get("var_threshold", 5000)
        var_95 = risk_data["var"]["historical_95"]
        if var_95 > var_threshold:
            alerts_fired.append(await self._fire_alert(
                user_id, config, "VAR_BREACH",
                f"VaR 95% (${var_95:,.0f}) exceeds threshold (${var_threshold:,.0f})",
                "HIGH", {"var_95": var_95, "threshold": var_threshold}
            ))

        # 2. Volatility threshold check
        vol_threshold = config.get("volatility_threshold", 30)
        annual_vol = risk_data["metrics"]["annual_volatility"]
        if annual_vol > vol_threshold:
            alerts_fired.append(await self._fire_alert(
                user_id, config, "VOLATILITY_SPIKE",
                f"Annual volatility ({annual_vol:.1f}%) exceeds threshold ({vol_threshold}%)",
                "MODERATE", {"annual_vol": annual_vol, "threshold": vol_threshold}
            ))

        # 3. Max drawdown threshold check
        dd_threshold = config.get("drawdown_threshold", 15)
        max_dd = risk_data["metrics"]["max_drawdown_pct"]
        if max_dd > dd_threshold:
            alerts_fired.append(await self._fire_alert(
                user_id, config, "DRAWDOWN_BREACH",
                f"Max drawdown ({max_dd:.1f}%) exceeds threshold ({dd_threshold}%)",
                "HIGH", {"max_dd": max_dd, "threshold": dd_threshold}
            ))

        # 4. Stress test severity check
        severity_trigger = config.get("stress_severity_trigger", "CRITICAL")
        severity_order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
        trigger_level = severity_order.get(severity_trigger, 3)
        critical_scenarios = [
            s for s in risk_data["stress_tests"]
            if severity_order.get(s["severity"], 0) >= trigger_level and s["impact_pct"] < -5
        ]
        if critical_scenarios:
            names = ", ".join(s["name"] for s in critical_scenarios[:3])
            worst = min(critical_scenarios, key=lambda s: s["impact_pct"])
            alerts_fired.append(await self._fire_alert(
                user_id, config, "STRESS_TEST_WARNING",
                f"{len(critical_scenarios)} stress scenarios at {severity_trigger}+ level: {names}. Worst impact: {worst['impact_pct']:.1f}%",
                "CRITICAL" if any(s["severity"] == "CRITICAL" for s in critical_scenarios) else "HIGH",
                {"scenarios": [s["name"] for s in critical_scenarios], "worst_impact": worst["impact_pct"]}
            ))

        # 5. Sharpe ratio degradation
        sharpe_threshold = config.get("sharpe_threshold", 0.5)
        sharpe = risk_data["metrics"]["sharpe_ratio"]
        if sharpe < sharpe_threshold:
            alerts_fired.append(await self._fire_alert(
                user_id, config, "SHARPE_DEGRADATION",
                f"Sharpe ratio ({sharpe:.3f}) below threshold ({sharpe_threshold})",
                "MODERATE", {"sharpe": sharpe, "threshold": sharpe_threshold}
            ))

        valid_alerts = [a for a in alerts_fired if a is not None]
        return {
            "checked": True,
            "alerts_fired": len(valid_alerts),
            "alerts": valid_alerts,
            "risk_snapshot": {
                "var_95": var_95,
                "annual_vol": annual_vol,
                "max_dd": max_dd,
                "sharpe": sharpe,
                "stress_critical_count": len(critical_scenarios)
            }
        }

    async def _fire_alert(self, user_id: str, config: Dict, alert_type: str,
                          message: str, severity: str, details: Dict) -> Optional[Dict]:
        # Cooldown: don't repeat same alert type within 30 minutes
        cooldown_key = f"{user_id}:{alert_type}"
        now = datetime.now(timezone.utc)
        last = self.last_alert_time.get(cooldown_key)
        if last and (now - last).total_seconds() < 1800:
            return None

        self.last_alert_time[cooldown_key] = now

        alert_doc = {
            "user_id": user_id,
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "details": details,
            "triggered_at": now.isoformat(),
            "acknowledged": False
        }
        await self.db.risk_alerts.insert_one({**alert_doc})

        # Send Telegram if enabled
        if config.get("telegram_push", True):
            severity_emoji = {
                "CRITICAL": "\U0001f6a8", "HIGH": "\U0001f534",
                "MODERATE": "\U0001f7e1", "LOW": "\U0001f7e2"
            }
            emoji = severity_emoji.get(severity, "\u26a0\ufe0f")
            tg_msg = (
                f"{emoji} <b>RISK ALERT: {alert_type.replace('_', ' ')}</b>\n\n"
                f"<b>Severity:</b> {severity}\n"
                f"{message}\n\n"
                f"<b>Time:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                f"#RiskAlert #PortfolioRisk"
            )
            await self.telegram.send_message(tg_msg)

        return alert_doc

    async def acknowledge_alert(self, user_id: str, alert_id: str) -> bool:
        from bson import ObjectId
        result = await self.db.risk_alerts.update_one(
            {"_id": ObjectId(alert_id), "user_id": user_id},
            {"$set": {"acknowledged": True, "acknowledged_at": datetime.now(timezone.utc).isoformat()}}
        )
        return result.modified_count > 0

    def _default_config(self, user_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "enabled": True,
            "var_threshold": 5000,
            "volatility_threshold": 30,
            "drawdown_threshold": 15,
            "sharpe_threshold": 0.5,
            "stress_severity_trigger": "CRITICAL",
            "telegram_push": True,
            "browser_push": True,
            "auto_check_interval": 300,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
