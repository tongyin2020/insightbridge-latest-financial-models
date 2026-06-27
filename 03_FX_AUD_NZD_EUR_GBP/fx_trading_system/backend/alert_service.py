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
        """Format and send a trade signal alert."""
        direction_emoji = {"BUY": "UP", "SELL": "DOWN", "WAIT": "PAUSE"}.get(signal.get("direction", ""), "?")
        confidence = signal.get("confidence", 0)
        pair = signal.get("pair", "???")
        regime = signal.get("regime", "???")
        reason = signal.get("reason", "")

        message = (
            f"<b>[{direction_emoji} SIGNAL] {pair}</b>\n"
            f"Direction: <b>{signal.get('direction', '?')}</b>\n"
            f"Confidence: <b>{confidence:.1f}%</b>\n"
            f"Regime: {regime}\n"
            f"Reason: {reason}\n"
            f"Time: {signal.get('timestamp', '?')}"
        )
        await self.send_telegram(message)

    async def alert_kill_switch(self, reason: str) -> None:
        """Send an urgent kill switch alert."""
        message = (
            f"<b>[KILL SWITCH ACTIVATED]</b>\n"
            f"Reason: {reason}\n"
            f"All trading has been halted.\n"
            f"Time: {datetime.now(timezone.utc).isoformat()}"
        )
        # Send twice for visibility
        await self.send_telegram(message)
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")

    async def alert_data_loss(self, source: str) -> None:
        """Send a data source failure alert."""
        message = (
            f"<b>[DATA LOSS WARNING]</b>\n"
            f"Source: {source}\n"
            f"Market data feed has been interrupted.\n"
            f"System is falling back to simulated data.\n"
            f"Time: {datetime.now(timezone.utc).isoformat()}"
        )
        await self.send_telegram(message)
        logger.warning(f"Data loss from source: {source}")

    async def alert_trade_executed(self, trade: dict) -> None:
        """Send a trade execution notification."""
        direction = trade.get("direction", "?")
        pair = trade.get("pair", "?")
        entry_price = trade.get("entry_price", 0)
        stop_loss = trade.get("stop_loss", 0)
        take_profit = trade.get("take_profit", 0)
        confidence = trade.get("confidence", 0)
        signal_type = trade.get("signal_type", "?")

        message = (
            f"<b>[TRADE EXECUTED] {pair}</b>\n"
            f"Direction: <b>{direction}</b>\n"
            f"Entry: {entry_price:.5f}\n"
            f"SL: {stop_loss:.5f} | TP: {take_profit:.5f}\n"
            f"Type: {signal_type} | Confidence: {confidence:.1f}%\n"
            f"Time: {trade.get('entry_time', '?')}"
        )
        await self.send_telegram(message)

    async def alert_trade_closed(self, trade: dict) -> None:
        """Send a trade closure notification."""
        pair = trade.get("pair", "?")
        pnl_pips = trade.get("pnl_pips", 0)
        pnl_usd = trade.get("pnl_usd", 0)
        result = "WIN" if pnl_pips > 0 else "LOSS" if pnl_pips < 0 else "BREAKEVEN"

        message = (
            f"<b>[TRADE CLOSED] {pair} - {result}</b>\n"
            f"PnL: {pnl_pips:+.1f} pips (${pnl_usd:+.2f})\n"
            f"Entry: {trade.get('entry_price', 0):.5f}\n"
            f"Exit: {trade.get('exit_price', 0):.5f}\n"
            f"Time: {trade.get('exit_time', '?')}"
        )
        await self.send_telegram(message)

    async def alert_event_state(self, event_state: dict) -> None:
        """Send event state change notification."""
        state = event_state.get("state", "?")
        title = event_state.get("event_title", "")
        level = event_state.get("event_level", "?")
        remaining = event_state.get("remaining_seconds", 0)

        message = (
            f"<b>[EVENT STATE: {state}]</b>\n"
            f"Event: {title}\n"
            f"Level: {level}\n"
            f"Remaining: {remaining:.0f}s\n"
            f"Time: {event_state.get('timestamp', '?')}"
        )
        await self.send_telegram(message)

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
