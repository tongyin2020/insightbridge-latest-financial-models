"""Step 2 · Phase A — IBKR Level-2 depth + tape collector (data plumbing only).

Turns a broker session into the microstructure inputs the Step-1 gates already
know how to read, but which the current snapshot-based loop never supplied:

  * ``fetch_depth(ib, contract, symbol)`` -> ``(bid_sizes, ask_sizes)`` from
    ``reqMktDepth`` (free Level-2 for FX / WTI / crypto on IBKR).
  * a rolling **near-side (top-of-book bid) size series** per symbol, so
    ``near_side_liquidity_crash`` has history to compare against.
  * a rolling **price/volume tape** (seeded from the 1-min bars the loop already
    fetches) so ``cumulative_volume_delta`` / ``cvd_top_divergence`` can run.

Design constraints (same as Step 1):
  * **Pure plumbing, no decisions.** This module never blocks or places orders.
  * **Fault-tolerant.** Every broker call is wrapped; any failure degrades to
    ``None`` / empty so the live loop is never disturbed and the gates simply
    see "cannot tell".
  * **Bar-approximated CVD is labelled.** True tick-rule CVD needs
    tick-by-tick trades; Phase A seeds the tape from bar closes (coarse but
    honest) and exposes ``tape_source`` so downstream logs say which it is.
    A tick-by-tick upgrade is a drop-in refinement.

Duck-typed against ib_insync: ``ib`` only needs ``reqMktDepth(contract,
numRows=...)`` returning an object with ``domBids`` / ``domAsks`` (each item has
``.size``), plus ``sleep(seconds)`` and (optionally) ``cancelMktDepth(contract)``.
This keeps it unit-testable with a fake ``ib`` and no TWS.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple


class DepthCollector:
    def __init__(self, levels: int = 5, history: int = 40,
                 depth_sleep: float = 4.0, poll_step: float = 0.25) -> None:
        self.levels = int(levels)
        self.history = int(history)
        # ``depth_sleep`` is the *max* time to wait for the async order book to
        # populate; we poll every ``poll_step`` and stop as soon as it fills.
        self.depth_sleep = float(depth_sleep)
        self.poll_step = float(poll_step)
        self._bid_size_hist: Dict[str, Deque[float]] = {}
        self._prices: Dict[str, Deque[float]] = {}
        self._volumes: Dict[str, Deque[float]] = {}
        self._tape_source: Dict[str, str] = {}
        self._last_depth: Dict[str, Dict[str, Any]] = {}

    # ── Level-2 depth ────────────────────────────────────────────────────────
    def fetch_depth(self, ib: Any, contract: Any, symbol: str
                    ) -> Tuple[Optional[List[float]], Optional[List[float]]]:
        """Return ``(bid_sizes, ask_sizes)`` (top ``levels`` resting sizes) or
        ``(None, None)`` if depth is unavailable. Also records the top bid size
        into the near-side history used by the liquidity-crash gate.

        ``reqMktDepth`` fills the book **asynchronously**, so a single fixed
        sleep often reads an empty ``domBids``/``domAsks``. We poll up to
        ``depth_sleep`` seconds and return as soon as the book has data."""
        try:
            tkr = ib.reqMktDepth(contract, numRows=self.levels)
            bid_sizes: List[float] = []
            ask_sizes: List[float] = []
            waited = 0.0
            step = self.poll_step if self.poll_step > 0 else self.depth_sleep
            while True:
                try:
                    ib.sleep(step)
                except Exception:           # noqa: BLE001
                    break
                waited += step
                bid_rows = self._levels(getattr(tkr, "domBids", None))
                ask_rows = self._levels(getattr(tkr, "domAsks", None))
                bid_sizes = [row["size"] for row in bid_rows]
                ask_sizes = [row["size"] for row in ask_rows]
                if bid_sizes or ask_sizes:
                    self._last_depth[symbol] = {
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        "bids": bid_rows, "asks": ask_rows,
                    }
                    break
                if waited >= self.depth_sleep:
                    break
            try:
                ib.cancelMktDepth(contract)
            except Exception:               # noqa: BLE001
                pass
        except Exception:                   # noqa: BLE001
            return (None, None)

        if bid_sizes:
            self._bid_size_hist.setdefault(
                symbol, deque(maxlen=self.history)).append(bid_sizes[0])
        return (bid_sizes or None, ask_sizes or None)

    def _sizes(self, dom: Any) -> List[float]:
        return [row["size"] for row in self._levels(dom)]

    def _levels(self, dom: Any) -> List[Dict[str, float]]:
        out: List[Dict[str, float]] = []
        for position, lvl in enumerate((dom or [])[: self.levels]):
            size = getattr(lvl, "size", None)
            price = getattr(lvl, "price", None)
            if size is None and isinstance(lvl, (int, float)):
                size = lvl
            try:
                if size is not None and float(size) >= 0:
                    out.append({
                        "level": int(position),
                        "price": float(price) if price is not None else 0.0,
                        "size": float(size),
                    })
            except (TypeError, ValueError):
                continue
        return out

    # ── price/volume tape (bar-seeded; tick-by-tick is a drop-in upgrade) ─────
    def update_tape_from_df(self, symbol: str, df: Any) -> None:
        """Seed/refresh the rolling price+volume tape from the loop's 1-min bars.
        Only the trailing ``history`` closes/volumes are kept. Labelled
        ``tape_source='bar_1m'`` so shadow logs never overstate granularity."""
        try:
            closes = [float(x) for x in df["close"].tolist()[-self.history:]]
            vols = [float(x) for x in df["volume"].tolist()[-self.history:]]
        except Exception:                   # noqa: BLE001
            return
        if not closes:
            return
        self._prices[symbol] = deque(closes, maxlen=self.history)
        self._volumes[symbol] = deque(vols, maxlen=self.history)
        self._tape_source[symbol] = "bar_1m"

    # ── accessors the gates/shadow consume ───────────────────────────────────
    def near_side_size_series(self, symbol: str) -> List[float]:
        return list(self._bid_size_hist.get(symbol, ()))

    def recent_prices(self, symbol: str) -> List[float]:
        return list(self._prices.get(symbol, ()))

    def recent_volumes(self, symbol: str) -> List[float]:
        return list(self._volumes.get(symbol, ()))

    def tape_source(self, symbol: str) -> str:
        return self._tape_source.get(symbol, "none")

    def last_depth_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        snapshot = self._last_depth.get(symbol)
        if snapshot is None:
            return None
        return {
            "observed_at": snapshot["observed_at"],
            "bids": [dict(row) for row in snapshot["bids"]],
            "asks": [dict(row) for row in snapshot["asks"]],
        }

    def raw_for_exit(self, symbol: str) -> Dict[str, Any]:
        """Assemble the ``pos.raw`` microstructure fields the capital-safety exit
        engine reads (``recent_prices`` / ``recent_volumes`` /
        ``near_side_size_series``)."""
        return {
            "recent_prices": self.recent_prices(symbol),
            "recent_volumes": self.recent_volumes(symbol),
            "near_side_size_series": self.near_side_size_series(symbol),
            "tape_source": self.tape_source(symbol),
        }
