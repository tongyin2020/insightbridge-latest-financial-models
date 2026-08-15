#!/usr/bin/env python3
"""Financial Agent System — Phase 0 entry point (observe-only by default)."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_system.adapters import BotFactory
from agent_system.config import AgentConfig
from agent_system.execution import ExecutionBridge
from agent_system.gatekeeper.macro_monitor import MacroMonitor
from agent_system.graph import CrisisGraph
from agent_system.persistence import TraceStore
from agent_system.reflection import ReflectionAgent
from agent_system.state import AgentState


def _serialize(obj: object) -> object:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def build_report(state: AgentState) -> str:
    lines = [
        f"# Financial Agent System Report",
        f"",
        f"- trace_id: `{state.trace_id}`",
        f"- ts: {state.ts.isoformat()}",
        f"- phase: **{state.phase}**",
        f"- base_dir: `{state.base_dir}`",
        f"",
        f"## Gatekeeper",
        f"",
    ]
    if state.gatekeeper:
        g = state.gatekeeper
        lines += [
            f"- score: `{g.score:.4f}` / threshold `{g.threshold:.4f}`",
            f"- phase: `{g.phase}`",
            f"- reason: {g.reason}",
            f"- factors:",
        ]
        for k, v in g.factors.items():
            lines.append(f"  - {k}: {v:.4f}")
    lines += ["", "## Bot Snapshots", ""]
    for bot_id, bot in state.bot_snapshots.items():
        lines.append(f"### {bot_id}")
        lines.append(f"- symbols: {', '.join(bot.symbols)}")
        lines.append(f"- open positions: {len(bot.open_positions)}")
        lines.append(f"- recent PnL abs: {bot.recent_pnl_abs}")
        lines.append(f"- shadow summary:")
        for k, v in bot.shadow_summary.items():
            lines.append(f"  - {k}: {v}")
        lines.append(f"- signal summary: {json.dumps(bot.signal_summary, ensure_ascii=False)}")
        lines.append("")
    if state.reports:
        lines += ["", "## Agent Reports", ""]
        for report_name, report_data in state.reports.items():
            if report_name == "consensus" or not isinstance(report_data, dict):
                continue
            lines.append(f"### {report_name}")
            signals = report_data.get("signals") or report_data.get("bots")
            if signals:
                for bot_id, details in signals.items():
                    lines.append(f"- **{bot_id}**: {details}")
            if "approved" in report_data:
                lines.append(f"- approved: {report_data['approved']}")
            if "vetoes" in report_data:
                lines.append(f"- vetoes: {report_data['vetoes']}")
            lines.append("")
    if state.recommendation:
        lines += ["", "## Recommendation", ""]
        lines.append(f"```json\n{json.dumps(state.recommendation, ensure_ascii=False, indent=2)}\n```")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InsightBridge Financial Agent System — Phase 0/1/2")
    parser.add_argument("--base-dir", default=None, help="Repo base directory")
    parser.add_argument("--crisis-threshold", type=float, default=None, help="Gatekeeper crisis threshold")
    parser.add_argument("--execution-enabled", action="store_true", help="DANGER: allow execution (default OFF)")
    parser.add_argument("--run-reflection", action="store_true", help="Also run post-market reflection")
    parser.add_argument("--report-path", default=None, help="Optional markdown report path")
    args = parser.parse_args(argv)

    cfg = AgentConfig.from_env(base_dir=Path(args.base_dir) if args.base_dir else None)
    if args.crisis_threshold is not None:
        cfg.crisis_threshold = args.crisis_threshold
    if args.execution_enabled:
        cfg.execution_enabled = True

    state = AgentState(
        ts=datetime.now(timezone.utc),
        base_dir=str(cfg.base_dir),
        trace_id=str(uuid.uuid4())[:8],
    )

    # Layer 1: Gatekeeper
    gatekeeper = MacroMonitor(cfg)
    state.gatekeeper = gatekeeper.evaluate()
    state.phase = state.gatekeeper.phase

    # Read bot snapshots
    factory = BotFactory(cfg)
    for bot in factory.all_bots():
        state.bot_snapshots[bot.bot_id] = bot.snapshot()

    # Layer 2/3: 危机研判子图（只在 CRISIS_AWAKEN 时激活）
    if state.phase == "CRISIS_AWAKEN":
        graph = CrisisGraph(cfg)
        state = graph.run(state)
    else:
        state.recommendation = {
            "action": "MONITOR",
            "note": "Phase 0/1/2: Gatekeeper 未触发危机，保持观察。",
            "execution_enabled": False,
        }

    # Layer 4: 执行桥（默认只预演挂单，不连接 IBKR）
    bridge = ExecutionBridge(cfg)
    execution_result = bridge.execute(
        state.recommendation or {},
        trace_id=state.trace_id,
        bot_snapshots=state.bot_snapshots,
    )
    state.recommendation = state.recommendation or {}
    state.recommendation["execution_result"] = execution_result

    # Persist
    trace = TraceStore(cfg.trace_dir)
    record = {
        "trace_id": state.trace_id,
        "ts": state.ts.isoformat(),
        "phase": state.phase,
        "crisis_score": state.gatekeeper.score if state.gatekeeper else 0.0,
        "gatekeeper": state.gatekeeper.__dict__ if state.gatekeeper else {},
        "bot_snapshots": {k: v.__dict__ for k, v in state.bot_snapshots.items()},
        "reports": state.reports,
        "recommendation": state.recommendation,
    }
    trace.append(record)

    # Print human-readable report to stdout
    print(build_report(state))

    if args.report_path:
        Path(args.report_path).write_text(build_report(state), encoding="utf-8")

    if args.run_reflection:
        reflect = ReflectionAgent(cfg)
        report_path = reflect.run(lookback_hours=24.0)
        print(f"\nReflection report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
