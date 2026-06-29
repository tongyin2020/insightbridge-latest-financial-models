from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_duration(start_raw: Optional[str], end_raw: Optional[str]) -> str:
    start = _parse_ts(start_raw)
    end = _parse_ts(end_raw)
    if not start or not end:
        return "unknown"
    seconds = max(0, int((end - start).total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class TradeTelegramNotifier:
    """Trade-only Telegram notifier.

    It sends messages only for real trade lifecycle events:
    - position truly opened / filled
    - position truly closed
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def _send(self, lines: list[str]) -> bool:
        if not self.enabled:
            return False
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat:
            return False
        payload = {
            "chat_id": chat,
            "text": "\n".join(lines),
            "disable_web_page_preview": True,
        }
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)  # noqa: S310
            return True
        except Exception:
            return False

    def notify_trade_open(self, symbol: str, direction: str, fill_price: float, quantity: Any) -> bool:
        return self._send(
            [
                "Trade Opened",
                f"Instrument: {symbol}",
                f"Direction: {direction}",
                f"Entry: {fill_price:.6f}",
                f"Quantity: {quantity}",
                f"Time: {_utc_now()}",
            ]
        )

    def notify_trade_close(
        self,
        symbol: str,
        direction: str,
        opened_at: Optional[str],
        closed_at: Optional[str],
        entry_price: Optional[float],
        exit_price: Optional[float],
        pnl_abs: Optional[float],
        pnl_pct: Optional[float],
    ) -> bool:
        pnl_abs = float(pnl_abs or 0.0)
        pnl_pct = float(pnl_pct or 0.0) * 100.0
        status = "PROFIT" if pnl_abs > 0 else "LOSS" if pnl_abs < 0 else "FLAT"
        return self._send(
            [
                "Trade Closed",
                f"Instrument: {symbol}",
                f"Direction: {direction}",
                f"Duration: {_format_duration(opened_at, closed_at)}",
                f"Entry: {float(entry_price or 0.0):.6f}",
                f"Exit: {float(exit_price or 0.0):.6f}",
                f"PnL Status: {status}",
                f"PnL: {pnl_abs:+.4f} ({pnl_pct:+.2f}%)",
                f"Time: {closed_at or _utc_now()}",
            ]
        )

    def build_close_payload(self, row: Dict[str, Any], close_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": row.get("symbol", ""),
            "direction": row.get("direction", ""),
            "opened_at": row.get("opened_at"),
            "closed_at": row.get("closed_at"),
            "entry_price": row.get("entry_price"),
            "exit_price": row.get("exit_price"),
            "pnl_abs": close_result.get("pnl_abs"),
            "pnl_pct": close_result.get("pnl_pct"),
        }
