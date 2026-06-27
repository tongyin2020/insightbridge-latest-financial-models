import os
import asyncio
import logging
import resend
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class EmailDigestService:
    """Sends daily email digest with risk summary, alerts, and AI market brief."""

    def __init__(self, db):
        self.db = db
        api_key = os.environ.get("RESEND_API_KEY", "")
        self.sender = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
        self.enabled = bool(api_key)
        if api_key:
            resend.api_key = api_key
            logger.info("Resend email service initialized")
        else:
            logger.warning("RESEND_API_KEY not set — email digest disabled")

    async def send_email(self, to: str, subject: str, html: str) -> Optional[str]:
        if not self.enabled:
            logger.warning("Email service not enabled")
            return None
        try:
            params = {"from": self.sender, "to": [to], "subject": subject, "html": html}
            result = await asyncio.to_thread(resend.Emails.send, params)
            logger.info(f"Email sent to {to}: {result.get('id', 'N/A')}")
            return result.get("id")
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return None

    async def get_email_preferences(self, user_id: str) -> Dict[str, Any]:
        prefs = await self.db.email_preferences.find_one({"user_id": user_id}, {"_id": 0})
        if not prefs:
            prefs = {
                "user_id": user_id,
                "digest_enabled": True,
                "digest_email": "",
                "include_risk_summary": True,
                "include_alerts": True,
                "include_ai_brief": True,
                "include_portfolio": True,
            }
        return prefs

    async def save_email_preferences(self, user_id: str, prefs: Dict[str, Any]) -> Dict[str, Any]:
        prefs["user_id"] = user_id
        prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.db.email_preferences.update_one(
            {"user_id": user_id}, {"$set": prefs}, upsert=True
        )
        return {k: v for k, v in prefs.items() if k != "_id"}

    async def generate_and_send_digest(self, user_id: str, user_email: str,
                                        risk_data: Dict, alerts: list,
                                        ai_brief: Dict, portfolio: Dict) -> Dict[str, Any]:
        prefs = await self.get_email_preferences(user_id)
        target_email = prefs.get("digest_email") or user_email
        if not prefs.get("digest_enabled", True):
            return {"sent": False, "reason": "Digest disabled"}

        subject = f"Bond Trading Daily Digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        html = self._build_digest_html(risk_data, alerts, ai_brief, portfolio, prefs)

        email_id = await self.send_email(target_email, subject, html)

        log = {
            "user_id": user_id,
            "email": target_email,
            "subject": subject,
            "email_id": email_id,
            "sent": email_id is not None,
            "sent_at": datetime.now(timezone.utc).isoformat()
        }
        await self.db.email_digest_logs.insert_one({**log})
        return {k: v for k, v in log.items() if k != "_id"}

    async def get_digest_history(self, user_id: str, limit: int = 10) -> list:
        logs = await self.db.email_digest_logs.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("sent_at", -1).limit(limit).to_list(limit)
        return logs

    def _build_digest_html(self, risk: Dict, alerts: list, brief: Dict,
                           portfolio: Dict, prefs: Dict) -> str:
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
        sections = []

        # AI Brief section
        if prefs.get("include_ai_brief", True) and brief:
            headline = brief.get("headline", "Daily Market Update")
            body = brief.get("body", "").replace("\n", "<br>")[:600]
            snap = brief.get("market_snapshot", {})
            sections.append(f"""
            <tr><td style="padding:20px;background:#1a1a2e;border-radius:4px;margin-bottom:12px;">
                <h2 style="color:#60a5fa;font-size:14px;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">AI Market Brief</h2>
                <p style="color:#f1f5f9;font-size:14px;font-weight:bold;margin:0 0 8px;">{headline}</p>
                <p style="color:#94a3b8;font-size:12px;line-height:1.6;margin:0 0 10px;">{body}</p>
                <table style="width:100%;"><tr>
                    <td style="color:#67e8f9;font-size:11px;font-family:monospace;">10Y: {snap.get('y10', 'N/A')}%</td>
                    <td style="color:#67e8f9;font-size:11px;font-family:monospace;">Slope: {snap.get('slope', 'N/A')}%</td>
                    <td style="color:#67e8f9;font-size:11px;font-family:monospace;">VIX: {snap.get('vix', 'N/A')}</td>
                </tr></table>
            </td></tr><tr><td style="height:12px;"></td></tr>""")

        # Risk summary section
        if prefs.get("include_risk_summary", True) and risk:
            var_data = risk.get("var", {})
            metrics = risk.get("metrics", {})
            sharpe_color = "#4ade80" if metrics.get("sharpe_ratio", 0) > 1 else "#fbbf24" if metrics.get("sharpe_ratio", 0) > 0 else "#f87171"
            sections.append(f"""
            <tr><td style="padding:20px;background:#1a1a2e;border-radius:4px;">
                <h2 style="color:#f87171;font-size:14px;margin:0 0 12px;text-transform:uppercase;letter-spacing:1px;">Risk Summary</h2>
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="padding:8px;border-bottom:1px solid #334155;color:#94a3b8;font-size:11px;">VaR 95%</td>
                        <td style="padding:8px;border-bottom:1px solid #334155;color:#f87171;font-size:13px;font-family:monospace;text-align:right;">${var_data.get('historical_95', 0):,.0f}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;border-bottom:1px solid #334155;color:#94a3b8;font-size:11px;">Annual Volatility</td>
                        <td style="padding:8px;border-bottom:1px solid #334155;color:#22d3ee;font-size:13px;font-family:monospace;text-align:right;">{metrics.get('annual_volatility', 0):.1f}%</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;border-bottom:1px solid #334155;color:#94a3b8;font-size:11px;">Max Drawdown</td>
                        <td style="padding:8px;border-bottom:1px solid #334155;color:#fb923c;font-size:13px;font-family:monospace;text-align:right;">{metrics.get('max_drawdown_pct', 0):.1f}%</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;color:#94a3b8;font-size:11px;">Sharpe Ratio</td>
                        <td style="padding:8px;color:{sharpe_color};font-size:13px;font-family:monospace;text-align:right;">{metrics.get('sharpe_ratio', 0):.3f}</td>
                    </tr>
                </table>
            </td></tr><tr><td style="height:12px;"></td></tr>""")

        # Alerts section
        if prefs.get("include_alerts", True) and alerts:
            severity_colors = {"CRITICAL": "#ef4444", "HIGH": "#f97316", "MODERATE": "#eab308", "LOW": "#22c55e"}
            alert_rows = ""
            for a in alerts[:5]:
                sev_color = severity_colors.get(a.get("severity", ""), "#94a3b8")
                alert_rows += f"""<tr>
                    <td style="padding:6px 8px;border-bottom:1px solid #334155;">
                        <span style="color:{sev_color};font-size:10px;font-weight:bold;text-transform:uppercase;">{a.get('severity', '')}</span>
                    </td>
                    <td style="padding:6px 8px;border-bottom:1px solid #334155;color:#e2e8f0;font-size:11px;">{a.get('alert_type', '').replace('_', ' ')}</td>
                    <td style="padding:6px 8px;border-bottom:1px solid #334155;color:#94a3b8;font-size:11px;">{a.get('message', '')[:80]}</td>
                </tr>"""
            sections.append(f"""
            <tr><td style="padding:20px;background:#1a1a2e;border-radius:4px;">
                <h2 style="color:#fbbf24;font-size:14px;margin:0 0 12px;text-transform:uppercase;letter-spacing:1px;">Recent Alerts ({len(alerts)})</h2>
                <table style="width:100%;border-collapse:collapse;">{alert_rows}</table>
            </td></tr><tr><td style="height:12px;"></td></tr>""")

        # Portfolio section
        if prefs.get("include_portfolio", True) and portfolio:
            total_eq = portfolio.get("total_equity", portfolio.get("total_value", 0))
            cash = portfolio.get("cash", 0)
            pnl = portfolio.get("unrealized_pnl", 0)
            pnl_color = "#4ade80" if pnl >= 0 else "#f87171"
            sections.append(f"""
            <tr><td style="padding:20px;background:#1a1a2e;border-radius:4px;">
                <h2 style="color:#a78bfa;font-size:14px;margin:0 0 12px;text-transform:uppercase;letter-spacing:1px;">Portfolio Snapshot</h2>
                <table style="width:100%;"><tr>
                    <td style="text-align:center;padding:10px;">
                        <div style="color:#94a3b8;font-size:10px;text-transform:uppercase;">Total Value</div>
                        <div style="color:#f1f5f9;font-size:18px;font-family:monospace;font-weight:bold;">${total_eq:,.0f}</div>
                    </td>
                    <td style="text-align:center;padding:10px;">
                        <div style="color:#94a3b8;font-size:10px;text-transform:uppercase;">Cash</div>
                        <div style="color:#f1f5f9;font-size:18px;font-family:monospace;font-weight:bold;">${cash:,.0f}</div>
                    </td>
                    <td style="text-align:center;padding:10px;">
                        <div style="color:#94a3b8;font-size:10px;text-transform:uppercase;">Unrealized P&L</div>
                        <div style="color:{pnl_color};font-size:18px;font-family:monospace;font-weight:bold;">{'+' if pnl >= 0 else ''}${pnl:,.0f}</div>
                    </td>
                </tr></table>
            </td></tr>""")

        body_content = "".join(sections) if sections else '<tr><td style="color:#94a3b8;padding:20px;">No data available for today\'s digest.</td></tr>'

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:Arial,Helvetica,sans-serif;">
<table style="width:100%;max-width:600px;margin:0 auto;background:#0f172a;">
    <tr><td style="padding:24px 20px 16px;text-align:center;">
        <h1 style="color:#f1f5f9;font-size:18px;margin:0;letter-spacing:2px;">BOND TRADING DAILY DIGEST</h1>
        <p style="color:#64748b;font-size:12px;margin:6px 0 0;">{date_str}</p>
    </td></tr>
    {body_content}
    <tr><td style="padding:20px;text-align:center;border-top:1px solid #1e293b;">
        <p style="color:#475569;font-size:10px;margin:0;">AI Bond & Rate Trading System | Powered by GPT-5.2</p>
    </td></tr>
</table></body></html>"""
