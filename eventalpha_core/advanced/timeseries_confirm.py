"""Step 2 · Phase D — zero-shot time-series confirmation (right-side second check).

═══════════════════════════════════════════════════════════════════════════════
IMPORTANT — every numeric default in this module is an UNVALIDATED PLACEHOLDER.
═══════════════════════════════════════════════════════════════════════════════
The confirmation thresholds (``min_prob_confirm`` etc.) are provisional priors so
the *mechanism* can run observe-only. They are NOT measured facts and must be
calibrated on real event history before any switch is turned on.

Idea: after Step-1's price/volume/OBI right-side confirmation says "enter", ask a
*pretrained zero-shot forecaster* (Amazon Chronos / Google TimesFM) whether the
next few bars are expected to continue in the signal's direction. This is a
second, model-based confirmation — it never initiates a trade, only agrees or
vetoes. It uses ordinary price history we already fetch (no paid data, no
dependency on the Level-2 shadow feed).

Design rules (mirror ``microstructure.py``):
  - Pure logic in :func:`right_side_confirmation`; forecaster is injected.
  - Heavy model deps (torch / chronos) are **lazily imported**; if unavailable we
    fall back to a dependency-free :class:`NaiveDriftForecaster` and label the
    backend honestly, so nothing is ever overstated and the live loop never breaks.
  - Degrades to "cannot tell" (``confirm=False`` with an explicit reason) whenever
    history is too short — never a hard failure.
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


# ── provisional, UNVALIDATED defaults ────────────────────────────────────────
@dataclass(frozen=True)
class TimeSeriesConfirmConfig:
    """Zero-shot confirmation parameters (all provisional placeholders)."""
    context_len: int = 64          # bars of history fed to the model
    horizon: int = 5               # bars ahead to forecast
    n_samples: int = 128           # sample paths (for probability estimate)
    min_prob_confirm: float = 0.55  # P(move in signal direction) to confirm
    min_expected_move_frac: float = 0.0  # require median forecast move >= this frac
    min_context: int = 16          # below this, decline to judge


@dataclass
class ForecastResult:
    """Sample paths from a forecaster. ``samples`` is ``n_samples`` paths, each of
    length ``horizon`` (absolute price levels, not returns)."""
    samples: List[List[float]]
    backend: str

    @property
    def finals(self) -> List[float]:
        return [s[-1] for s in self.samples if s]

    @property
    def median_final(self) -> Optional[float]:
        f = self.finals
        return statistics.median(f) if f else None


class NaiveDriftForecaster:
    """Dependency-free baseline: Monte-Carlo geometric random walk seeded from the
    context's own log-return drift + volatility. NOT a foundation model — it exists
    so the observe-only plumbing works (and tests run) before torch/chronos is
    installed. Labelled ``backend="naive"`` so it is never mistaken for Chronos."""

    backend = "naive"

    def __init__(self, seed: Optional[int] = 7) -> None:
        self._rng = random.Random(seed)

    def forecast(self, context: Sequence[float], horizon: int,
                 n_samples: int) -> ForecastResult:
        ctx = [float(x) for x in context if x is not None and float(x) > 0.0]
        if len(ctx) < 2:
            raise ValueError("context too short for naive forecaster")
        rets = [math.log(ctx[i] / ctx[i - 1]) for i in range(1, len(ctx))]
        drift = statistics.fmean(rets)
        vol = statistics.pstdev(rets) if len(rets) > 1 else 0.0
        last = ctx[-1]
        samples: List[List[float]] = []
        for _ in range(max(1, n_samples)):
            price = last
            path: List[float] = []
            for _ in range(horizon):
                shock = self._rng.gauss(drift, vol) if vol > 0 else drift
                price *= math.exp(shock)
                path.append(price)
            samples.append(path)
        return ForecastResult(samples=samples, backend=self.backend)


class ChronosForecaster:
    """Amazon Chronos zero-shot wrapper (lazy import). Raises ``ImportError`` at
    construction if ``chronos``/``torch`` are unavailable, so :func:`build_forecaster`
    can fall back cleanly."""

    backend = "chronos"

    def __init__(self, model_name: str = "amazon/chronos-bolt-small") -> None:
        import torch  # noqa: F401  (lazy; may be absent)
        from chronos import ChronosPipeline  # type: ignore
        self._torch = torch
        self._pipe = ChronosPipeline.from_pretrained(model_name)

    def forecast(self, context: Sequence[float], horizon: int,
                 n_samples: int) -> ForecastResult:
        ctx = [float(x) for x in context if x is not None]
        tensor = self._torch.tensor(ctx)
        # Chronos returns shape [n_series, n_samples, horizon]; we pass one series.
        fc = self._pipe.predict(tensor, prediction_length=horizon,
                                num_samples=max(1, n_samples))
        paths = fc[0].tolist()  # n_samples x horizon
        return ForecastResult(samples=[[float(v) for v in p] for p in paths],
                              backend=self.backend)


def build_forecaster(backend: str = "auto",
                     seed: Optional[int] = 7):
    """Return a forecaster. ``auto`` tries Chronos then falls back to naive.
    Never raises: an unavailable heavy backend degrades to the naive baseline."""
    b = (backend or "auto").lower()
    if b in ("chronos", "auto"):
        try:
            return ChronosForecaster()
        except Exception:                       # noqa: BLE001
            if b == "chronos":
                # explicit request failed -> still degrade, but caller sees backend
                return NaiveDriftForecaster(seed=seed)
    return NaiveDriftForecaster(seed=seed)


def right_side_confirmation(
    prices: Sequence[float],
    direction: str,
    forecaster,
    config: TimeSeriesConfirmConfig = TimeSeriesConfirmConfig(),
) -> Tuple[bool, str, dict]:
    """Ask the forecaster whether the next ``horizon`` bars are expected to
    continue in ``direction``. Returns ``(confirm, reason, meta)``.

    LONG confirms when P(price_up at horizon) >= ``min_prob_confirm`` and the
    median forecast move is at least ``min_expected_move_frac``. SHORT is mirrored.
    Declines with ``confirm=False`` (never an exception) on short history.
    """
    d = (direction or "").upper()
    meta: dict = {"backend": getattr(forecaster, "backend", "unknown")}
    clean = [float(x) for x in prices if x is not None and float(x) > 0.0]
    if len(clean) < config.min_context:
        return False, "insufficient_history", meta
    context = clean[-config.context_len:]
    last = context[-1]
    try:
        fc = forecaster.forecast(context, config.horizon, config.n_samples)
    except Exception as exc:                     # noqa: BLE001
        meta["error"] = str(exc)
        return False, "forecast_unavailable", meta
    finals = fc.finals
    if not finals or last <= 0.0:
        return False, "empty_forecast", meta
    prob_up = sum(1 for f in finals if f > last) / len(finals)
    prob_down = sum(1 for f in finals if f < last) / len(finals)
    median_final = fc.median_final
    exp_move = (median_final / last - 1.0) if median_final else 0.0
    meta.update({
        "backend": fc.backend,
        "prob_up": round(prob_up, 4),
        "prob_down": round(prob_down, 4),
        "expected_move_frac": round(exp_move, 6),
        "horizon": config.horizon,
        "n_context": len(context),
        "n_samples": len(finals),
    })
    if d in ("LONG", "BUY"):
        meta["prob_dir"] = round(prob_up, 4)
        if prob_up >= config.min_prob_confirm and exp_move >= config.min_expected_move_frac:
            return True, f"ts_confirm_long_p{prob_up:.2f}", meta
        return False, f"ts_veto_long_p{prob_up:.2f}", meta
    if d in ("SHORT", "SELL"):
        meta["prob_dir"] = round(prob_down, 4)
        if prob_down >= config.min_prob_confirm and (-exp_move) >= config.min_expected_move_frac:
            return True, f"ts_confirm_short_p{prob_down:.2f}", meta
        return False, f"ts_veto_short_p{prob_down:.2f}", meta
    return False, "direction_flat_or_unknown", meta
