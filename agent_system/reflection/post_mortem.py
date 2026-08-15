from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from agent_system.config import AgentConfig


class ReflectionAgent:
    """收盘后复盘 Agent：读真实交易日志和 Agent trace，输出 Markdown 复盘报告。"""

    def __init__(self, config: AgentConfig) -> None:
        self.cfg = config
        self.db_path = config.base_dir / "data.db"
        self.trace_path = config.trace_dir / "agent_trace.jsonl"
        self.report_path = config.trace_dir / f"reflection_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"

    def _read_trades(self, lookback_hours: float = 24.0) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        try:
            with sqlite3.connect(str(self.db_path), timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM trades WHERE opened_at >= ? ORDER BY opened_at DESC",
                    (cutoff.isoformat(),),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def _read_traces(self, n: int = 100) -> list[dict[str, Any]]:
        if not self.trace_path.exists():
            return []
        try:
            with self.trace_path.open("r", encoding="utf-8") as fh:
                lines = [line.strip() for line in fh if line.strip()]
            records: list[dict[str, Any]] = []
            for line in lines[-n:]:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return records
        except Exception:
            return []

    @staticmethod
    def _parse_ts(ts: str) -> datetime:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return datetime.now(timezone.utc)

    def _bot_stats(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        if not trades:
            return {"note": "复盘窗口内无真实交易记录"}
        stats: dict[str, list[dict[str, Any]]] = {}
        for t in trades:
            bot = t.get("model", t.get("symbol", "unknown"))
            stats.setdefault(bot, []).append(t)

        result: dict[str, Any] = {}
        for bot, ts in stats.items():
            closed = [t for t in ts if t.get("status") == "CLOSED"]
            pnls = [t.get("pnl_abs", 0.0) or 0.0 for t in closed]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]
            result[bot] = {
                "total_trades": len(ts),
                "open_positions": len([t for t in ts if t.get("status") == "OPEN"]),
                "realized_pnl": round(sum(pnls), 2),
                "win_rate": round(len(wins) / len(pnls), 2) if pnls else 0.0,
                "avg_win": round(mean(wins), 2) if wins else 0.0,
                "avg_loss": round(mean(losses), 2) if losses else 0.0,
                "max_drawdown": round(min(pnls), 2) if pnls else 0.0,
            }
        return result

    def _attribute(self, trades: list[dict[str, Any]], traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """把每笔交易归因到最近 30 分钟内、方向一致的一条 Agent  recommendation。"""
        attributions: list[dict[str, Any]] = []
        for trade in trades:
            trade_ts = self._parse_ts(trade.get("opened_at", ""))
            trade_dir = trade.get("direction", "")
            trade_sym = trade.get("symbol", "")
            best: tuple[timedelta, dict[str, Any] | None, dict[str, Any] | None] = (
                timedelta(days=1),
                None,
                None,
            )
            for rec in traces:
                rec_ts = self._parse_ts(rec.get("ts", ""))
                gap = abs(trade_ts - rec_ts)
                if gap > timedelta(minutes=30):
                    continue
                rec_action = rec.get("recommendation", {}) or {}
                for action in rec_action.get("actions", []):
                    if action.get("direction") == trade_dir and action.get("symbol") == trade_sym:
                        if gap < best[0]:
                            best = (gap, trade, rec)
            attributions.append({
                "trade": trade,
                "matched_trace": best[2],
                "time_gap_minutes": best[0].total_seconds() / 60.0 if best[2] else None,
            })
        return attributions

    def run(self, lookback_hours: float = 24.0) -> Path:
        trades = self._read_trades(lookback_hours)
        traces = self._read_traces(n=200)
        stats = self._bot_stats(trades)
        attributions = self._attribute(trades, traces)

        lines = [
            "# Financial Agent System — Reflection Report",
            "",
            f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
            f"- base_dir: `{self.cfg.base_dir}`",
            f"- trades in last {lookback_hours}h: {len(trades)}",
            "",
            "## Bot Performance",
            "",
            "```json",
            json.dumps(stats, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "## Trace-to-Trade Attribution",
            "",
        ]
        if not attributions:
            lines.append("_No trades to attribute in the lookback window._")
        for a in attributions:
            t = a["trade"]
            trace = a["matched_trace"]
            if trace:
                lines.append(
                    f"- `{t.get('symbol')}` {t.get('direction')} "
                    f"PnL={t.get('pnl_abs')} | matched trace {trace.get('trace_id')} "
                    f"({a['time_gap_minutes']:.1f} min before)"
                )
            else:
                lines.append(
                    f"- `{t.get('symbol')}` {t.get('direction')} "
                    f"PnL={t.get('pnl_abs')} | no matching agent trace found"
                )

        lines += ["", "## Improvement Notes", ""]
        notes: list[str] = []
        for bot, s in stats.items():
            if isinstance(s, dict) and s.get("win_rate", 1.0) < 0.4 and s.get("total_trades", 0) >= 3:
                notes.append(f"- `{bot}` win rate {s['win_rate']} 连续亏损，建议收紧 critic/risk 阈值。")
        if not notes:
            notes.append("- 样本不足或无连续亏损，暂不提供自动调参建议。")
        lines.extend(notes)
        lines.append("")

        self.report_path.write_text("\n".join(lines), encoding="utf-8")
        return self.report_path


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="InsightBridge Financial Agent Reflection")
    parser.add_argument("--base-dir", default=None)
    parser.add_argument("--lookback-hours", type=float, default=24.0)
    args = parser.parse_args()
    base = Path(args.base_dir) if args.base_dir else Path(__file__).resolve().parent.parent.parent
    cfg = AgentConfig.from_env(base_dir=base)
    agent = ReflectionAgent(cfg)
    path = agent.run(lookback_hours=args.lookback_hours)
    print(f"Reflection report written to: {path}")


if __name__ == "__main__":
    main()
