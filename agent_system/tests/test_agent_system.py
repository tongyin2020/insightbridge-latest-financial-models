import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agent_system.adapters import BotFactory
from agent_system.config import AgentConfig
from agent_system.execution import ExecutionBridge
from agent_system.gatekeeper.macro_monitor import MacroMonitor
from agent_system.graph import CrisisGraph
from agent_system.reflection import ReflectionAgent
from agent_system.state import AgentState


def _make_base(tmp: Path) -> Path:
    (tmp / "reports" / "runtime").mkdir(parents=True)
    db = tmp / "data.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                client_ref TEXT PRIMARY KEY,
                symbol TEXT,
                direction TEXT,
                status TEXT,
                entry_price REAL,
                quantity REAL,
                pnl_abs REAL,
                pnl_pct REAL,
                opened_at TEXT,
                closed_at TEXT
            )
        """)
    return tmp


def _write_log(tmp: Path, name: str, records: list[dict]) -> None:
    path = tmp / "reports" / "runtime" / name
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def test_gatekeeper_returns_phase(tmp_path):
    base = _make_base(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    _write_log(base, "news_shadow.log", [
        {"ts": now, "would_wake": True, "is_relevant": True,
         "confidence": 0.9, "text": "Iran missile strike oil", "reason": "geopolitical"},
    ])
    _write_log(base, "timeseries_shadow.log", [
        {"ts": now, "symbol": "CL", "expected_move_frac": 0.04, "would_confirm": True},
    ])
    _write_log(base, "microstructure_shadow.log", [
        {"ts": now, "symbol": "CL", "would_reject_fakeout": False,
         "would_flag_cvd_divergence": False, "would_force_exit_liquidity_crash": True},
    ])
    _write_log(base, "continuous.log", [])

    cfg = AgentConfig(base_dir=base)
    monitor = MacroMonitor(cfg)
    result = monitor.evaluate()
    assert result.phase == "CRISIS_AWAKEN"
    assert result.score > cfg.crisis_threshold
    assert "oil" in result.reason.lower() or result.factors["news"] > 0


def test_gatekeeper_monitor_when_calm(tmp_path):
    base = _make_base(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    _write_log(base, "news_shadow.log", [
        {"ts": now, "would_wake": False, "is_relevant": False,
         "confidence": 0.2, "text": "Fed lunch", "reason": "not macro"},
    ])
    _write_log(base, "timeseries_shadow.log", [
        {"ts": now, "symbol": "MES", "expected_move_frac": 0.001, "would_confirm": False},
    ])
    _write_log(base, "microstructure_shadow.log", [])
    _write_log(base, "continuous.log", [])

    cfg = AgentConfig(base_dir=base)
    monitor = MacroMonitor(cfg)
    result = monitor.evaluate()
    assert result.phase == "MONITOR"
    assert result.score < cfg.crisis_threshold


def test_bot_adapter_reads_db_and_shadows(tmp_path):
    base = _make_base(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(base / "data.db")) as conn:
        conn.execute("""
            INSERT INTO trades (client_ref, symbol, direction, status,
                                entry_price, quantity, pnl_abs, pnl_pct,
                                opened_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("btc-1", "BTC", "LONG", "CLOSED", 65000.0, 0.1, 120.0, 0.018, now, now))
    _write_log(base, "timeseries_shadow.log", [
        {"ts": now, "symbol": "BTC", "expected_move_frac": 0.02, "would_confirm": True},
    ])
    _write_log(base, "microstructure_shadow.log", [
        {"ts": now, "symbol": "BTC", "would_reject_fakeout": True,
         "would_flag_cvd_divergence": False, "would_force_exit_liquidity_crash": False},
    ])
    _write_log(base, "news_shadow.log", [])
    _write_log(base, "continuous.log", [])

    cfg = AgentConfig(base_dir=base)
    factory = BotFactory(cfg)
    bot = factory.get("crypto")
    snap = bot.snapshot()
    assert snap.bot_id == "crypto"
    assert snap.latest_trade is not None
    assert snap.latest_trade["symbol"] == "BTC"
    assert snap.shadow_summary["microstructure_fakeout"] == 1


def test_crisis_graph_runs_and_produces_recommendation(tmp_path):
    base = _make_base(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    _write_log(base, "news_shadow.log", [
        {"ts": now, "would_wake": True, "is_relevant": True,
         "confidence": 0.85, "text": "Iran tensions hit oil", "reason": "geopolitical",
         "sentiment": "risk_on", "category": "GEOPOL", "affected_symbols": ["CL"]},
        {"ts": now, "would_wake": True, "is_relevant": True,
         "confidence": 0.90, "text": "EIA crude draw sparks supply fears", "reason": "inventory draw",
         "sentiment": "risk_on", "category": "EIA", "affected_symbols": ["CL"]},
    ])
    _write_log(base, "timeseries_shadow.log", [
        {"ts": now, "symbol": "CL", "expected_move_frac": 0.05, "would_confirm": True},
    ])
    _write_log(base, "microstructure_shadow.log", [
        {"ts": now, "symbol": "CL", "would_reject_fakeout": False,
         "would_flag_cvd_divergence": False, "would_force_exit_liquidity_crash": False},
    ])
    _write_log(base, "continuous.log", [])

    cfg = AgentConfig(base_dir=base)
    gatekeeper = MacroMonitor(cfg).evaluate()
    assert gatekeeper.phase == "CRISIS_AWAKEN"

    factory = BotFactory(cfg)
    state = AgentState(
        ts=datetime.now(timezone.utc),
        base_dir=str(base),
        phase="CRISIS_AWAKEN",
        gatekeeper=gatekeeper,
    )
    for bot in factory.all_bots():
        state.bot_snapshots[bot.bot_id] = bot.snapshot()

    graph = CrisisGraph(cfg)
    result = graph.run(state)
    assert result.recommendation is not None
    assert "actions" in result.recommendation
    assert result.recommendation["observe_only"] is True


def test_execution_bridge_stages_orders(tmp_path):
    base = _make_base(tmp_path)
    cfg = AgentConfig(base_dir=base)
    bridge = ExecutionBridge(cfg)
    recommendation = {
        "actions": [
            {"bot_id": "oil", "direction": "BUY", "symbol": "CL", "suggested_size": 1.0, "confidence": 0.8},
            {"bot_id": "crypto", "direction": "HOLD", "symbol": "BTC"},
        ]
    }
    result = bridge.execute(recommendation, trace_id="t-001")
    assert result["status"] == "no_action" if result["staged"] == 0 else "staged"
    assert all(a["direction"] in ("BUY", "SELL") for a in result.get("signals", []))
    # Default observe_only -> no live routing
    assert result["live"] is False


def test_reflection_agent_writes_report(tmp_path):
    base = _make_base(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(base / "data.db")) as conn:
        conn.execute("""
            INSERT INTO trades (client_ref, symbol, direction, status,
                                entry_price, quantity, pnl_abs, pnl_pct,
                                opened_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("cl-1", "CL", "LONG", "CLOSED", 75.0, 1.0, 120.0, 0.018, now, now))
    cfg = AgentConfig(base_dir=base)
    agent = ReflectionAgent(cfg)
    path = agent.run(lookback_hours=24.0)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "CL" in text and "120" in text
