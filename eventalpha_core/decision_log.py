"""Structured per-decision audit log for EventAlpha.

Engineering standard (Developer Edition spec): "Log every decision with
probabilities, thresholds, confidence, memory score, and realized PnL."

Every call to the brain that results in a real candidate decision should be
written here as one JSON object per line (JSONL). Entries are self-contained and
append-only so a run can be replayed/audited after the fact and joined to the
realized outcome once the trade closes.

Usage:
    logger = DecisionLogger(path)                       # append mode
    ref = logger.log_decision(event, state, decision)   # at decision time
    ...
    logger.log_outcome(ref, realized_pnl_bps=..., ...)  # when the trade closes
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import EventDecision, MacroEvent, MarketState


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DecisionRef:
    """Handle returned at decision time; pass it to log_outcome() to link the
    realized result back to the exact decision row."""

    decision_id: str
    event_id: str
    asset: str
    symbol: str


class DecisionLogger:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, row: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def log_decision(
        self,
        event: MacroEvent,
        state: MarketState,
        decision: EventDecision,
        *,
        rank_score: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> DecisionRef:
        meta = decision.metadata or {}
        decision_id = uuid.uuid4().hex
        row: Dict[str, Any] = {
            "kind": "decision",
            "decision_id": decision_id,
            "logged_at": _now_iso(),
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "event_title": event.title,
            "event_timestamp_utc": event.timestamp_utc,
            "asset": state.asset.value,
            "symbol": state.symbol,
            # decision outputs
            "action": decision.action.value,
            "grade": decision.grade.value,
            "direction": decision.direction.value,
            # probabilities / thresholds / confidence
            "severity_raw_score": decision.raw_score,
            "calibrated_confidence": decision.calibrated_confidence,
            "execution_confidence": decision.execution_confidence,
            "action_band": meta.get("action_band"),
            "wait_seconds": decision.wait_seconds,
            "max_wait_seconds": meta.get("max_wait_seconds"),
            "max_risk_fraction": decision.max_risk_fraction,
            # memory score
            "memory_edge": _extract_reason_value(decision, "memory_edge"),
            "cross_asset_alignment": state.cross_asset_alignment,
            "news_alignment": state.news_alignment,
            # selectivity / impact
            "early_move_bps": meta.get("early_move_bps"),
            "impact_bucket": meta.get("impact_bucket"),
            "impact_scaled_window": meta.get("impact_scaled_window"),
            "selectivity_enabled": meta.get("selectivity_enabled"),
            "selectivity_applied": meta.get("selectivity_applied"),
            # regime
            "macro_regime": meta.get("macro_regime"),
            "macro_regime_probabilities": meta.get("macro_regime_probabilities"),
            # bookkeeping
            "rank_score": rank_score,
            "reasons": decision.reasons,
        }
        if extra:
            row["extra"] = extra
        self._append(row)
        return DecisionRef(decision_id, event.event_id, state.asset.value, state.symbol)

    def log_outcome(
        self,
        ref: DecisionRef,
        *,
        realized_pnl_bps: Optional[float] = None,
        realized_pnl_pct: Optional[float] = None,
        mfe_bps: Optional[float] = None,
        mae_bps: Optional[float] = None,
        seconds_in_trade: Optional[int] = None,
        exit_reason: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        row: Dict[str, Any] = {
            "kind": "outcome",
            "decision_id": ref.decision_id,
            "logged_at": _now_iso(),
            "event_id": ref.event_id,
            "asset": ref.asset,
            "symbol": ref.symbol,
            "realized_pnl_bps": realized_pnl_bps,
            "realized_pnl_pct": realized_pnl_pct,
            "mfe_bps": mfe_bps,
            "mae_bps": mae_bps,
            "seconds_in_trade": seconds_in_trade,
            "exit_reason": exit_reason,
        }
        if extra:
            row["extra"] = extra
        self._append(row)


def _extract_reason_value(decision: EventDecision, key: str) -> Optional[float]:
    prefix = f"{key}="
    for r in decision.reasons:
        if r.startswith(prefix):
            try:
                return float(r[len(prefix):])
            except ValueError:
                return None
    return None
