from __future__ import annotations

from dataclasses import dataclass
from math import log, exp
from typing import Dict, List


@dataclass
class BayesianSignal:
    name: str
    probability: float
    weight: float
    reason: str = ""


@dataclass
class BayesianDecision:
    posterior: float
    log_odds: float
    signals_used: List[str]
    action_band: str


def _clip(p: float) -> float:
    return max(0.01, min(0.99, p))


def _logit(p: float) -> float:
    p = _clip(p)
    return log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + exp(-x))


def combine_signals(prior: float, signals: List[BayesianSignal]) -> BayesianDecision:
    """Weighted Bayesian-style evidence combiner.

    This is designed for macro event decisions, where signals are noisy and
    sparse. It is safer than a black-box average because every signal can be
    inspected and capped.
    """
    lo = _logit(prior)
    used = []
    for s in signals:
        w = max(0.0, min(2.0, s.weight))
        lo += w * (_logit(s.probability) - _logit(0.50))
        used.append(f"{s.name}:{s.probability:.2f}x{s.weight:.2f}")
    posterior = _sigmoid(max(-4.5, min(4.5, lo)))
    if posterior < 0.70:
        band = "watch_only"
    elif posterior < 0.80:
        band = "small_probe"
    elif posterior < 0.88:
        band = "normal_position"
    else:
        band = "heavy_candidate_requires_confirmation"
    return BayesianDecision(posterior=posterior, log_odds=lo, signals_used=used, action_band=band)


def default_event_signals(macro_direction: float, news: float, price_confirmation: float, cross_asset: float, liquidity: float, memory: float) -> List[BayesianSignal]:
    return [
        BayesianSignal("macro_direction", macro_direction, 1.00),
        BayesianSignal("news_semantics", news, 0.85),
        BayesianSignal("price_confirmation", price_confirmation, 1.10),
        BayesianSignal("cross_asset_confirmation", cross_asset, 1.15),
        BayesianSignal("liquidity_quality", liquidity, 0.75),
        BayesianSignal("event_memory_edge", memory, 0.65),
    ]
