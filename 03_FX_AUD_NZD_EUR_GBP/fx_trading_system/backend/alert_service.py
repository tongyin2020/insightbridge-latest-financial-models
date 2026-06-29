"""
Alert service: sends notifications via Telegram and falls back to console logging.
"""
from __future__ import annotations

import logging
import httpx
from datetime import datetime, timezone
from typing import Optional
from config import settings

logger = logging.getLogger("fx_alerts")


class AlertService:
    """Sends alerts via Telegram Bot API or logs to console as fallback."""

    TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def send_telegram(self, message: str) -> bool:
        """
        Send a message via Telegram Bot API.
        Returns True if sent successfully, False otherwise.
        """
        if not settings.telegram_configured:
            logger.info(f"[TELEGRAM FALLBACK] {message}")
            return False

        client = await self._get_client()
        url = f"{self.TELEGRAM_API_BASE.format(token=settings.telegram_bot_token)}/sendMessage"

        try:
            resp = await client.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Telegram API error: {data}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            logger.info(f"[TELEGRAM FALLBACK] {message}")
            return False

    async def alert_signal(self, signal: dict) -> None:
        """Silence signal alerts; only real trade open/close notifications are allowed."""
        return None

    async def alert_kill_switch(self, reason: str) -> None:
        """Silence non-trade alerts; log only."""
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
        return None

    async def alert_data_loss(self, source: str) -> None:
        """Silence non-trade alerts; log only."""
        logger.warning(f"Data loss from source: {source}")
        return None

    async def alert_trade_executed(self, trade: dict) -> None:
        """Send a real trade execution notification."""
        direction = trade.get("direction", "?")
        pair = trade.get("pair", "?")
        entry_price = trade.get("entry_price", 0)
        amount = trade.get("amount", trade.get("size", trade.get("quantity", "?")))

        message = (
            f"<b>[TRADE OPENED] {pair}</b>\n"
            f"Direction: <b>{direction}</b>\n"
            f"Entry: {entry_price:.5f}\n"
            f"Amount: <b>{amount}</b>\n"
            f"Time: {trade.get('entry_time', '?')}"
        )
        await self.send_telegram(message)

    async def alert_trade_closed(self, trade: dict) -> None:
        """Send a real trade closure notification."""
        pair = trade.get("pair", "?")
        pnl_pips = trade.get("pnl_pips", 0)
        pnl_usd = trade.get("pnl_usd", 0)
        result = "PROFIT" if pnl_pips > 0 else "LOSS" if pnl_pips < 0 else "FLAT"
        duration = trade.get("duration", "unknown")

        message = (
            f"<b>[TRADE CLOSED] {pair}</b>\n"
            f"Duration: <b>{duration}</b>\n"
            f"PnL Status: <b>{result}</b>\n"
            f"PnL: {pnl_pips:+.1f} pips (${pnl_usd:+.2f})\n"
            f"Time: {trade.get('exit_time', '?')}"
        )
        await self.send_telegram(message)

    async def alert_event_state(self, event_state: dict) -> None:
        """Silence event-state alerts; only real trade open/close notifications are allowed."""
        return None

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
