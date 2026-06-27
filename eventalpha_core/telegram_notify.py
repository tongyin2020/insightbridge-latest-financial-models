from __future__ import annotations

import hashlib
import html
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib import parse, request


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_local_env(env_path: Path) -> Dict[str, str]:
    if not env_path.exists():
        return {}
    values: Dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        values[key] = value
    return values


@dataclass
class TelegramNotifyConfig:
    enabled: bool
    bot_token: str
    chat_id: str
    api_url: str
    dedupe_minutes: int
    state_file: Path


class EventAlphaTelegramNotifier:
    def __init__(self, base_dir: Path) -> None:
        local_env = _load_local_env(base_dir / ".env.telegram.local")
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", local_env.get("TELEGRAM_BOT_TOKEN", "")).strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", local_env.get("TELEGRAM_CHAT_ID", "")).strip()
        reports_dir = base_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        self.config = TelegramNotifyConfig(
            enabled=bool(bot_token and chat_id),
            bot_token=bot_token,
            chat_id=chat_id,
            api_url=f"https://api.telegram.org/bot{bot_token}/sendMessage" if bot_token else "",
            dedupe_minutes=int(os.environ.get("EVENTALPHA_TELEGRAM_DEDUPE_MINUTES", "30")),
            state_file=reports_dir / "eventalpha_telegram_alert_state.json",
        )

    def _load_state(self) -> Dict[str, Any]:
        if not self.config.state_file.exists():
            return {"recent_alerts": []}
        try:
            return json.loads(self.config.state_file.read_text())
        except Exception:
            return {"recent_alerts": []}

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.config.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    def _fingerprint(self, payload: Dict[str, Any]) -> str:
        raw = "|".join(
            [
                str(payload.get("event_type", "")),
                str(payload.get("title", "")),
                str(payload.get("asset", "")),
                str(payload.get("symbol", "")),
                str(payload.get("action", "")),
                str(payload.get("direction", "")),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _should_send(self, fingerprint: str) -> bool:
        state = self._load_state()
        recent = state.get("recent_alerts", [])
        cutoff = _utc_now() - timedelta(minutes=self.config.dedupe_minutes)
        keep = []
        blocked = False
        for row in recent:
            try:
                sent_at = datetime.fromisoformat(row["sent_at"])
            except Exception:
                continue
            if sent_at >= cutoff:
                keep.append(row)
            if row.get("fingerprint") == fingerprint and sent_at >= cutoff:
                blocked = True
        state["recent_alerts"] = keep
        self._save_state(state)
        return not blocked

    def _mark_sent(self, fingerprint: str, payload: Dict[str, Any]) -> None:
        state = self._load_state()
        recent = state.get("recent_alerts", [])
        recent.append(
            {
                "fingerprint": fingerprint,
                "sent_at": _utc_now().isoformat(),
                "payload": payload,
            }
        )
        state["recent_alerts"] = recent[-100:]
        self._save_state(state)

    def _render_message(self, payload: Dict[str, Any]) -> str:
        reasons = payload.get("reasons", [])
        lines = [
            "<b>EventAlpha Trade Alert</b>",
            "",
            f"<b>Event</b>: {html.escape(str(payload.get('event_type', '')).upper())}",
            f"<b>Title</b>: {html.escape(str(payload.get('title', '')))}",
            f"<b>Asset</b>: {html.escape(str(payload.get('asset', '')))}",
            f"<b>Symbol</b>: {html.escape(str(payload.get('symbol', '')))}",
            f"<b>Action</b>: {html.escape(str(payload.get('action', '')))}",
            f"<b>Direction</b>: {html.escape(str(payload.get('direction', '')))}",
            f"<b>Confidence</b>: {float(payload.get('execution_confidence', 0.0)):.2%}",
            f"<b>Wait</b>: {int(payload.get('wait_seconds', 0))}s",
            f"<b>Risk Fraction</b>: {float(payload.get('max_risk_fraction', 0.0)):.4f}",
        ]
        if payload.get("rank_score") is not None:
            lines.append(f"<b>Rank Score</b>: {float(payload.get('rank_score', 0.0)):.4f}")
        if payload.get("execution_status"):
            lines.append(f"<b>Execution</b>: {html.escape(str(payload.get('execution_status')))}")
        if payload.get("position_id"):
            lines.append(f"<b>Position ID</b>: {html.escape(str(payload.get('position_id')))}")
        if payload.get("notional") is not None:
            lines.append(f"<b>Planned Notional</b>: {float(payload.get('notional', 0.0)):.2f}")
        if reasons:
            lines.append("<b>Reasons</b>:")
            for reason in reasons[:6]:
                lines.append(f"• {html.escape(str(reason))}")
        return "\n".join(lines)

    def send_trade_alert(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config.enabled:
            return {"sent": False, "reason": "telegram_not_configured"}
        fingerprint = self._fingerprint(payload)
        if not self._should_send(fingerprint):
            return {"sent": False, "reason": "deduped"}
        body = parse.urlencode(
            {
                "chat_id": self.config.chat_id,
                "text": self._render_message(payload),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = request.Request(self.config.api_url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        self._mark_sent(fingerprint, payload)
        return {"sent": True, "reason": "ok", "response": raw}

    def send_for_entries(
        self,
        *,
        event_type: str,
        title: str,
        decisions: List[Dict[str, Any]],
        executions: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        execution_map = {}
        for row in executions or []:
            key = (row.get("asset"), row.get("result", {}).get("execution_plan", {}).get("symbol"))
            execution_map[key] = row.get("result", {})
        results = []
        for row in decisions:
            decision = row.get("decision", {})
            action = str(decision.get("action", ""))
            if action not in {"enter_small", "enter_normal", "enter_heavy"}:
                continue
            exec_result = execution_map.get((row.get("asset"), row.get("symbol")), {})
            exec_plan = exec_result.get("execution_plan", {})
            payload = {
                "event_type": event_type,
                "title": title,
                "asset": row.get("asset"),
                "symbol": row.get("symbol"),
                "action": action,
                "direction": decision.get("direction"),
                "execution_confidence": decision.get("execution_confidence", 0.0),
                "wait_seconds": decision.get("wait_seconds", 0),
                "max_risk_fraction": decision.get("max_risk_fraction", 0.0),
                "rank_score": row.get("rank_score"),
                "execution_status": exec_result.get("status"),
                "position_id": exec_result.get("position_id"),
                "notional": exec_plan.get("notional"),
                "reasons": decision.get("reasons", []),
            }
            result = self.send_trade_alert(payload)
            result["payload"] = payload
            results.append(result)
        return results
