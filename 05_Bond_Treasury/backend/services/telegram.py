import os
import logging
import httpx
from datetime import datetime, timezone
from models.schemas import TradingSignal

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)
        self.http_client = None

    async def initialize(self):
        if self.enabled:
            self.http_client = httpx.AsyncClient()
            logger.info("Telegram notifier initialized")

    async def close(self):
        if self.http_client:
            await self.http_client.aclose()

    async def send_message(self, message: str, parse_mode: str = "HTML"):
        if not self.enabled or not self.http_client:
            logger.warning("Telegram notifier not enabled")
            return False
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": message, "parse_mode": parse_mode}
            response = await self.http_client.post(url, json=payload)
            if response.status_code == 200:
                logger.info("Telegram notification sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False

    async def send_signal_alert(self, signal: TradingSignal):
        emoji = "\U0001f7e2" if "BUY" in signal.signal_type.value or "LONG" in signal.signal_type.value else "\U0001f534"
        message = f"""{emoji} <b>NEW TRADING SIGNAL</b>\n\n<b>Type:</b> {signal.signal_type.value}\n<b>Confidence:</b> {signal.confidence:.2%}\n<b>Strategy:</b> {signal.strategy or 'AI_HYBRID'}\n<b>Time:</b> {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n<i>{signal.ai_reasoning or 'AI analysis based signal'}</i>\n\n#TradingSignal #AITrading"""
        await self.send_message(message)

    async def send_execution_alert(self, signal: TradingSignal, price: float):
        message = f"""\u2705 <b>TRADE EXECUTED</b>\n\n<b>Type:</b> {signal.signal_type.value}\n<b>Price:</b> {price:.4f}\n<b>Confidence:</b> {signal.confidence:.2%}\n<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n#TradeExecution #AITrading"""
        await self.send_message(message)

    async def send_risk_alert(self, risk_type: str, message_text: str):
        message = f"""\u26a0\ufe0f <b>RISK ALERT: {risk_type}</b>\n\n{message_text}\n\n<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n#RiskAlert #TradingRisk"""
        await self.send_message(message)

    async def send_system_alert(self, status: str, details: str):
        emoji = "\U0001f534" if status == "HALT" else "\U0001f7e1" if status == "WARNING" else "\U0001f7e2"
        message = f"""{emoji} <b>SYSTEM STATUS: {status}</b>\n\n{details}\n\n<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n#SystemAlert #TradingSystem"""
        await self.send_message(message)
