"""Phase 4b: observe-only ("shadow") wiring of the v2 telemetry adapters into the
live TWS loop.

This validates the Phase-4 adapters against a real IB Gateway *without ever
touching orders or the live decision*. When enabled it, per scan, converts the
already-fetched broker inputs (isConnected / bid / ask / sizes / feed lag) into
the v2 objects, runs the ExecutionQualityGate, and appends one JSONL line so we
can inspect whether quote_age / latency / spread / liquidity / gate verdicts look
sane on the paper feed before anything is ever wired into real trading.

Default OFF. Enable with ``EVENTALPHA_V2_TELEMETRY=1`` (or pass ``enabled=True``).
Import is fault-tolerant: if ``eventalpha_core.v2`` is unavailable the observer
degrades to a no-op so it can never break the live loop.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_V2_OK = True
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from eventalpha_core.v2.telemetry import (
        ExecutionState, RejectRateTracker, spread_bps_from_quote,
        liquidity_score_from_sizes)
    from eventalpha_core.v2.execution_quality_gate import ExecutionQualityGate
except Exception:                       # noqa: BLE001
    _V2_OK = False
    ExecutionState = None
    RejectRateTracker = None
    spread_bps_from_quote = None
    liquidity_score_from_sizes = None
    ExecutionQualityGate = None


def _enabled_from_env() -> bool:
    return os.environ.get(
        "EVENTALPHA_V2_TELEMETRY", "").lower() in {"1", "true", "yes", "on"}


class V2TelemetryShadow:
    """Observe-only telemetry recorder. Never places, modifies, or blocks orders."""

    def __init__(self, enabled: Optional[bool] = None,
                 log_path: Optional[str] = None):
        if enabled is None:
            enabled = _enabled_from_env()
        # Only truly active when explicitly enabled AND the v2 package imported.
        self.enabled = bool(enabled) and _V2_OK
        self.v2_ok = _V2_OK
        self.log_path = Path(log_path) if log_path else None
        self.rejects = RejectRateTracker() if _V2_OK else None
        self.gate = ExecutionQualityGate() if _V2_OK else None
        self.n_observed = 0

    def record_order_status(self, status: str) -> None:
        """Feed order outcomes so the rolling reject rate reflects the real venue."""
        if self.rejects is not None:
            self.rejects.record(status)

    def observe(self, symbol: str, connected: bool,
                bid: Optional[float], ask: Optional[float],
                bid_size: Optional[float] = None, ask_size: Optional[float] = None,
                latency_s: float = 0.0, tick_epoch: Optional[float] = None,
                now_epoch: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Build the v2 objects from one scan's broker inputs, run the
        execution-quality gate, log a JSONL line, and return the record. Returns
        ``None`` (and does nothing) when disabled. Fail-safe: any error is swallowed
        so the live loop is never disturbed."""
        if not self.enabled:
            return None
        try:
            now = now_epoch if now_epoch is not None else datetime.now(
                timezone.utc).timestamp()
            reject_rate = self.rejects.rate() if self.rejects is not None else 0.0
            state = ExecutionState.from_ticker(
                connected=connected, tick_epoch=tick_epoch, now_epoch=now,
                latency_s=latency_s, recent_reject_rate=reject_rate)
            spread = spread_bps_from_quote(bid, ask)
            liq = liquidity_score_from_sizes(bid_size, ask_size)
            verdict = self.gate.evaluate(state)
            rec = {
                "stage": "v2_telemetry_shadow",
                "ts": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "connected": bool(connected),
                "quote_age_s": round(state.quote_age_s, 3),
                "latency_s": round(state.latency_s, 3),
                "recent_reject_rate": round(state.recent_reject_rate, 4),
                "spread_bps": (round(spread, 3) if spread is not None else None),
                "liquidity_score": round(liq, 3),
                "exec_gate_allowed": bool(verdict.allowed),
                "exec_quality_score": round(verdict.quality_score, 3),
                "exec_gate_reason": verdict.reason,
            }
            self.n_observed += 1
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            return rec
        except Exception:               # noqa: BLE001
            return None
