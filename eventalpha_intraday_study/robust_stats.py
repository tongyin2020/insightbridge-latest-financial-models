"""Small-sample statistics for the event study.

We have ~60 events per asset. Point estimates (a 61% win rate, a +5 bps mean) are
almost meaningless at that size without an honest uncertainty band and a
significance test that does not assume normality. This module provides the
classical, distribution-free tools that actually move the needle here:

  * bootstrap_ci        -- non-parametric CI for any statistic (mean, win rate).
  * permutation_test    -- exact-ish significance for "policy A beats policy B"
                           without a normality assumption (label reshuffling).
  * benjamini_hochberg  -- multiple-hypothesis correction; testing many
                           asset x scenario cells inflates false positives.
  * beta_binomial_posterior -- Bayesian win-rate estimate that shrinks toward the
                           prior when n is small, with a credible interval.

All functions are deterministic given ``seed``.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
from scipy import stats


def bootstrap_ci(x: Sequence[float], stat: Callable[[np.ndarray], float] = np.mean,
                 n_boot: int = 10000, alpha: float = 0.05,
                 seed: int = 0) -> dict:
    """Percentile bootstrap CI for ``stat`` of a 1-D sample."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return {"point": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(n_boot, x.size))
    sample = x[idx]
    if stat is np.mean:                        # vectorized fast paths (hot in SA)
        boot = sample.mean(axis=1)
    elif stat is win_rate:
        boot = (sample > 0).mean(axis=1)
    else:
        boot = np.array([stat(row) for row in sample])
    lo, hi = np.quantile(boot, [alpha / 2, 1 - alpha / 2])
    return {"point": float(stat(x)), "lo": float(lo), "hi": float(hi), "n": int(x.size)}


def win_rate(x: Sequence[float]) -> float:
    x = np.asarray(x, dtype=float)
    return float((x > 0).mean()) if x.size else float("nan")


def permutation_test(a: Sequence[float], b: Sequence[float],
                     stat: Callable[[np.ndarray, np.ndarray], float] | None = None,
                     n_perm: int = 10000, seed: int = 0) -> dict:
    """Two-sided permutation test of H0: a and b are exchangeable.

    Default statistic is the difference in means. Returns the observed statistic
    and a two-sided p-value from reshuffling the pooled labels.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0:
        return {"observed": float("nan"), "p_value": float("nan"),
                "n_a": int(a.size), "n_b": int(b.size)}
    if stat is None:
        def stat(u, v):  # noqa: E306
            return float(np.mean(u) - np.mean(v))
    obs = stat(a, b)
    pooled = np.concatenate([a, b])
    na = a.size
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        s = stat(pooled[:na], pooled[na:])
        if abs(s) >= abs(obs) - 1e-12:
            count += 1
    p = (count + 1) / (n_perm + 1)     # add-one smoothing (never reports p=0)
    return {"observed": float(obs), "p_value": float(p),
            "n_a": int(na), "n_b": int(b.size)}


def benjamini_hochberg(pvals: Sequence[float], alpha: float = 0.05) -> dict:
    """Benjamini-Hochberg FDR control. Returns per-test reject flags and q-values
    aligned to the input order."""
    p = np.asarray(pvals, dtype=float)
    m = p.size
    if m == 0:
        return {"reject": np.array([], dtype=bool), "qvalues": np.array([])}
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * m / (np.arange(1, m + 1))
    q = np.minimum.accumulate(q[::-1])[::-1]       # enforce monotonicity
    q = np.clip(q, 0, 1)
    reject_sorted = ranked <= (np.arange(1, m + 1) / m) * alpha
    if reject_sorted.any():
        kmax = np.max(np.where(reject_sorted))
        reject_sorted[:kmax + 1] = True
    reject = np.zeros(m, dtype=bool)
    qvalues = np.empty(m, dtype=float)
    reject[order] = reject_sorted
    qvalues[order] = q
    return {"reject": reject, "qvalues": qvalues}


def beta_binomial_posterior(wins: int, n: int, a0: float = 1.0, b0: float = 1.0,
                            cred: float = 0.95) -> dict:
    """Posterior win-rate under a Beta(a0,b0) prior (default uniform).

    The posterior mean shrinks the raw win rate toward the prior when n is small;
    the credible interval is the honest uncertainty band.
    """
    wins = int(wins)
    n = int(n)
    a = a0 + wins
    b = b0 + (n - wins)
    lo = float(stats.beta.ppf((1 - cred) / 2, a, b))
    hi = float(stats.beta.ppf(1 - (1 - cred) / 2, a, b))
    return {
        "raw_win_rate": (wins / n) if n else float("nan"),
        "posterior_mean": a / (a + b),
        "lo": lo, "hi": hi, "wins": wins, "n": n,
    }
