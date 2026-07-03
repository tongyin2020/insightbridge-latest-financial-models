"""Phase 4: real broker/venue telemetry adapters for the v2 gates.

Phases 1-3 ran the v2 stack on replay with proxy features and *no* execution
telemetry, so the Execution-Quality gate was never exercised and spread/liquidity
were neutral defaults. This module turns raw IBKR inputs into the exact objects
the v2 gates consume:

  * ``ExecutionState``            -> ExecutionQualityGate (connected / quote_age_s /
                                     latency_s / recent_reject_rate)
  * ``spread_bps_from_quote``     -> MarketState.spread_bps (RiskGate + EV cost)
  * ``liquidity_score_from_sizes``-> MarketState.liquidity_score (OpportunityEngine)
  * ``RejectRateTracker``         -> rolling recent reject rate from order outcomes

Everything here is pure Python with no ``ib_insync`` import, so it is unit-testable
offline and safe to import from the live path. It is NOT wired into live trading;
a caller must explicitly build these and pass them to ``V2DecisionOrchestrator``.

Wiring sketch for ``execution_framework/run_tws_continuous.py`` (opt-in):

    from eventalpha_core.v2.telemetry import (
        ExecutionState, RejectRateTracker, spread_bps_from_quote,
        liquidity_score_from_sizes)

    rejects = RejectRateTracker()            # update on each order outcome
    ...
    tkr = sess.ib.reqMktData(rc.raw, snapshot=True); sess.ib.sleep(1.0)
    now = time.time()
    exec_state = ExecutionState.from_ticker(
        connected=sess.ib.isConnected(),
        tick_epoch=(tkr.time.timestamp() if tkr.time else None),
        now_epoch=now,
        latency_s=account_state["feed_lag_ms"] / 1000.0,
        recent_reject_rate=rejects.rate())
    spread_bps = spread_bps_from_quote(tkr.bid, tkr.ask)
    liq = liquidity_score_from_sizes(tkr.bidSize, tkr.askSize)
    # then feed exec_state to orchestrator.decide(..., execution_state=exec_state)
    # and spread_bps / liq into the MarketState you build.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionState:
    """Broker/venue conditions consumed by ExecutionQualityGate. Field names match
    the gate's getattr contract exactly."""
    connected: bool = False
    quote_age_s: float = 999.0
    latency_s: float = 999.0
    recent_reject_rate: float = 1.0

    @classmethod
    def from_ticker(cls, connected: bool, tick_epoch: Optional[float],
                    now_epoch: float, latency_s: float,
                    recent_reject_rate: float) -> "ExecutionState":
        """Build from a broker snapshot. ``quote_age_s`` is now minus the last tick
        timestamp; a missing tick time is treated as maximally stale (safe)."""
        if tick_epoch is None:
            quote_age = 999.0
        else:
            quote_age = max(0.0, float(now_epoch) - float(tick_epoch))
        return cls(
            connected=bool(connected),
            quote_age_s=quote_age,
            latency_s=max(0.0, float(latency_s)),
            recent_reject_rate=min(1.0, max(0.0, float(recent_reject_rate))),
        )


class RejectRateTracker:
    """Rolling fraction of recent orders that were rejected/cancelled by the venue.

    Feed each order's outcome as it resolves; ``rate()`` is the reject fraction over
    the last ``window`` orders (0.0 until ``min_samples`` are seen, so a cold start
    does not look like a broken venue)."""

    _REJECTED = {"rejected", "cancelled", "canceled", "apicancelled", "inactive"}

    def __init__(self, window: int = 50, min_samples: int = 5):
        self.window = int(window)
        self.min_samples = int(min_samples)
        self._events: deque[bool] = deque(maxlen=self.window)

    def record(self, status: str) -> None:
        self._events.append(str(status).strip().lower() in self._REJECTED)

    def record_bool(self, rejected: bool) -> None:
        self._events.append(bool(rejected))

    def rate(self) -> float:
        if len(self._events) < self.min_samples:
            return 0.0
        return sum(self._events) / len(self._events)


def spread_bps_from_quote(bid: Optional[float], ask: Optional[float]
                          ) -> Optional[float]:
    """Live L1 spread in bps of the mid. ``None`` when the quote is missing/crossed
    so callers can decline rather than trade on a bad book."""
    if bid is None or ask is None:
        return None
    bid, ask = float(bid), float(ask)
    if bid <= 0.0 or ask <= 0.0 or ask < bid:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0.0:
        return None
    return (ask - bid) / mid * 1e4


def liquidity_score_from_sizes(bid_size: Optional[float], ask_size: Optional[float],
                               ref_size: float = 0.0,
                               imbalance_weight: float = 0.35) -> float:
    """Map top-of-book sizes to a 0..1 liquidity score for the OpportunityEngine.

    Combines depth (available size vs a reference size) with book balance (a lopsided
    book is worse to cross). Returns a neutral 0.5 when sizes are unavailable so it
    neither blocks nor flatters a decision."""
    if not bid_size or not ask_size or bid_size <= 0 or ask_size <= 0:
        return 0.5
    bid_size, ask_size = float(bid_size), float(ask_size)
    total = bid_size + ask_size
    imbalance = abs(bid_size - ask_size) / total          # 0 balanced .. 1 lopsided
    balance_score = 1.0 - imbalance
    if ref_size and ref_size > 0:
        depth_score = min(1.0, (min(bid_size, ask_size)) / float(ref_size))
    else:
        depth_score = 1.0
    score = (1.0 - imbalance_weight) * depth_score + imbalance_weight * balance_score
    return float(max(0.0, min(1.0, score)))
