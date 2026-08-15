from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from agent_system.config import AgentConfig
from agent_system.state import BotSnapshot
from agent_system.utils import recent_jsonl


class BotAdapter:
    def __init__(self, bot_id: str, symbols: list[str], config: AgentConfig) -> None:
        self.bot_id = bot_id
        self.symbols = symbols
        self.cfg = config

    @property
    def db_path(self) -> str:
        return str(self.cfg.base_dir / "data.db")

    def _query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except Exception:
            return []

    def _latest_trades(self) -> list[dict[str, Any]]:
        if not self.symbols:
            return []
        placeholders = ",".join("?" * len(self.symbols))
        return self._query(
            f"""
            SELECT * FROM trades
            WHERE symbol IN ({placeholders})
            ORDER BY opened_at DESC
            LIMIT 50
            """,
            tuple(self.symbols),
        )

    def _shadow_summary(self) -> dict[str, Any]:
        lookback = self.cfg.log_window_minutes
        base = self.cfg.base_dir / "reports" / "runtime"
        news = recent_jsonl(base / "news_shadow.log", self.cfg.news_lookback_minutes)
        ts = recent_jsonl(base / "timeseries_shadow.log", lookback)
        ms = recent_jsonl(base / "microstructure_shadow.log", lookback)

        symbol_set = set(self.symbols)

        news_relevant = [
            r for r in news
            if (set(r.get("affected_symbols", [])) & symbol_set)
            or any(sym in (r.get("text") or "") for sym in symbol_set)
        ]
        wake_count = sum(1 for r in news_relevant if r.get("would_wake"))

        ts_relevant = [r for r in ts if r.get("symbol") in symbol_set]
        confirm_count = sum(1 for r in ts_relevant if r.get("would_confirm"))
        avg_move = (
            sum(float(r.get("expected_move_frac", 0)) for r in ts_relevant) / len(ts_relevant)
            if ts_relevant else 0.0
        )

        ms_relevant = [r for r in ms if r.get("symbol") in symbol_set]
        fakeout = sum(1 for r in ms_relevant if r.get("would_reject_fakeout"))
        cvd_div = sum(1 for r in ms_relevant if r.get("would_flag_cvd_divergence"))
        liq_crash = sum(1 for r in ms_relevant if r.get("would_force_exit_liquidity_crash"))

        return {
            "window_minutes": lookback,
            "news_total": len(news),
            "news_relevant": len(news_relevant),
            "news_would_wake": wake_count,
            "timeseries_total": len(ts),
            "timeseries_relevant": len(ts_relevant),
            "timeseries_confirm": confirm_count,
            "timeseries_avg_expected_move_frac": round(avg_move, 6),
            "microstructure_total": len(ms),
            "microstructure_relevant": len(ms_relevant),
            "microstructure_fakeout": fakeout,
            "microstructure_cvd_divergence": cvd_div,
            "microstructure_liquidity_crash": liq_crash,
        }

    def snapshot(self) -> BotSnapshot:
        trades = self._latest_trades()
        open_positions = [t for t in trades if t.get("status") == "OPEN"]
        closed = [t for t in trades if t.get("status") == "CLOSED"]
        recent_pnl_abs = sum(t.get("pnl_abs", 0.0) or 0.0 for t in closed[:20])
        recent_pnl_pct = (
            sum(t.get("pnl_pct", 0.0) or 0.0 for t in closed[:20]) / len(closed[:20])
            if closed[:20] else 0.0
        )
        latest = trades[0] if trades else None

        directions = Counter(str(t.get("direction", "")) for t in trades)
        dom_dir = directions.most_common(1)[0][0] if directions else "neutral"

        shadow = self._shadow_summary()

        return BotSnapshot(
            bot_id=self.bot_id,
            symbols=self.symbols,
            latest_trade=latest,
            open_positions=open_positions,
            recent_pnl_abs=round(recent_pnl_abs, 2),
            recent_pnl_pct=round(recent_pnl_pct, 4),
            shadow_summary=shadow,
            signal_summary={
                "dominant_direction": dom_dir,
                "recent_trades": len(trades),
                "open_count": len(open_positions),
            },
        )


class BotFactory:
    def __init__(self, config: AgentConfig) -> None:
        self.cfg = config

    def all_bots(self) -> list[BotAdapter]:
        return [
            BotAdapter("crypto", self.cfg.bot_symbols["crypto"], self.cfg),
            BotAdapter("fx", self.cfg.bot_symbols["fx"], self.cfg),
            BotAdapter("bond", self.cfg.bot_symbols["bond"], self.cfg),
            BotAdapter("oil", self.cfg.bot_symbols["oil"], self.cfg),
            BotAdapter("index", self.cfg.bot_symbols["index"], self.cfg),
        ]

    def get(self, bot_id: str) -> BotAdapter:
        symbols = self.cfg.bot_symbols.get(bot_id, [])
        return BotAdapter(bot_id, symbols, self.cfg)
