"""Quantum-inspired optimizer: simulated annealing.

Simulated annealing is the classical thermal analogue of quantum annealing -- it
attacks the same rugged, non-convex optimization landscapes (selecting a
threshold, a subset of assets, a set of weights) that quantum annealers target,
but it runs on an ordinary CPU today with no NISQ-era hardware noise. It is the
practical, available way to do the kind of optimization the "let a quantum
computer help with the math" idea points at.

We use it to choose the per-asset early-move entry threshold that maximises a
*robust* objective (bootstrap lower confidence bound of net P&L, penalised for
too few trades) rather than the in-sample point estimate -- so the optimizer
cannot chase a lucky 3-trade cell.

The routine is generic (`anneal`) and deterministic given ``seed``.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np


def anneal(objective: Callable[[np.ndarray], float], x0: Sequence[float],
           bounds: Sequence[tuple[float, float]], *, maximize: bool = True,
           steps: int = 3000, t0: float = 1.0, cooling: float = 0.997,
           step_frac: float = 0.15, seed: int = 0) -> dict:
    """Maximise (or minimise) ``objective`` over a box via simulated annealing.

    Metropolis acceptance with a geometric cooling schedule. Proposals are
    Gaussian steps scaled to each dimension's range. Returns the best point found,
    its value, and the acceptance rate.
    """
    rng = np.random.default_rng(seed)
    x = np.array(x0, dtype=float)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    x = np.clip(x, lo, hi)
    scale = (hi - lo) * step_frac

    sign = 1.0 if maximize else -1.0
    cur = objective(x)
    best_x, best = x.copy(), cur
    t = t0
    accepts = 0
    for _ in range(steps):
        cand = np.clip(x + rng.normal(0.0, 1.0, size=x.shape) * scale, lo, hi)
        val = objective(cand)
        delta = sign * (val - cur)
        if delta >= 0 or rng.random() < np.exp(delta / max(t, 1e-12)):
            x, cur = cand, val
            accepts += 1
            if sign * (cur - best) > 0:
                best_x, best = x.copy(), cur
        t *= cooling
    return {"x": best_x, "value": float(best),
            "accept_rate": accepts / steps, "steps": steps}
