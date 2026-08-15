from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class GatekeeperResult:
    ts: datetime
    phase: str  # "MONITOR" | "CRISIS_AWAKEN"
    score: float
    threshold: float
    factors: dict[str, float] = field(default_factory=dict)
    reason: str = ""


@dataclass
class BotSnapshot:
    bot_id: str
    symbols: list[str] = field(default_factory=list)
    latest_trade: Optional[dict[str, Any]] = None
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    recent_pnl_abs: float = 0.0
    recent_pnl_pct: float = 0.0
    shadow_summary: dict[str, Any] = field(default_factory=dict)
    signal_summary: dict[str, Any] = field(default_factory=dict)
    allowed: bool = True


@dataclass
class AgentState:
    ts: datetime
    base_dir: str
    phase: str = "MONITOR"
    crisis_score: float = 0.0
    gatekeeper: Optional[GatekeeperResult] = None
    bot_snapshots: dict[str, BotSnapshot] = field(default_factory=dict)
    recommendation: Optional[dict[str, Any]] = None
    trace_id: str = ""
