"""Deterministic, data-free self-checks for the execution model, robust stats,
and the quantum-inspired optimizer. Run: python3 -m eventalpha_intraday_study.test_execution_robustness
"""
from __future__ import annotations

import numpy as np

from . import execution_model as em
from . import robust_stats as rs
from . import qi_optimizer as qi


def test_execution_costs_penalise():
    secs = np.arange(0, 60, dtype=float)
    price = np.full_like(secs, 100.0)          # flat mid -> gross round trip = 0
    c = em.ExecCosts(half_spread_bps=1.0, event_spread_mult=1.0, event_spread_secs=0.0,
                     slippage_bps=1.0, commission_bps=2.0, latency_s=0.0)
    for d in (1, -1):
        r = em.fills(secs, price, entry_idx=2, exit_idx=40, direction=d, costs=c)
        assert abs(r["gross_bps"]) < 1e-6, r
        # ~ -(2*(spread+slip) + 2*commission) = -(2*2 + 4) = -8 bps
        assert -9.0 < r["net_bps"] < -7.0, r
        assert r["net_bps"] < r["gross_bps"]
    print("✓ execution costs degrade a flat round trip to ~-8 bps (both directions)")


def test_latency_is_adverse():
    secs = np.arange(0, 60, dtype=float)
    price = 100.0 + 0.01 * secs                # rising path
    c0 = em.ExecCosts(0.0, 1.0, 0.0, 0.0, 0.0, latency_s=0.0)
    c1 = em.ExecCosts(0.0, 1.0, 0.0, 0.0, 0.0, latency_s=5.0)
    r0 = em.fills(secs, price, 2, 40, direction=1, costs=c0)
    r1 = em.fills(secs, price, 2, 40, direction=1, costs=c1)
    # buying into a rising market with delay fills higher -> worse net
    assert r1["net_bps"] < r0["net_bps"], (r0, r1)
    print("✓ latency fills adversely on a trending path")


def test_bootstrap_ci_covers_mean():
    rng = np.random.default_rng(0)
    x = rng.normal(5.0, 2.0, size=2000)
    ci = rs.bootstrap_ci(x, np.mean, n_boot=2000, seed=1)
    assert ci["lo"] < 5.0 < ci["hi"], ci
    assert abs(ci["point"] - x.mean()) < 1e-9
    print(f"✓ bootstrap CI covers the true mean: {ci['lo']:.2f}..{ci['hi']:.2f}")


def test_permutation_separates():
    rng = np.random.default_rng(0)
    same_a = rng.normal(0, 1, 200); same_b = rng.normal(0, 1, 200)
    p_same = rs.permutation_test(same_a, same_b, n_perm=2000, seed=1)["p_value"]
    far_a = rng.normal(3, 1, 200); far_b = rng.normal(0, 1, 200)
    p_far = rs.permutation_test(far_a, far_b, n_perm=2000, seed=1)["p_value"]
    assert p_same > 0.2, p_same
    assert p_far < 0.01, p_far
    print(f"✓ permutation test: p(same)={p_same:.2f} >> p(separated)={p_far:.4f}")


def test_benjamini_hochberg():
    p = [0.001, 0.2, 0.03, 0.8]
    bh = rs.benjamini_hochberg(p, alpha=0.05)
    assert bh["reject"][0] and not bh["reject"][3], bh["reject"]
    assert (bh["qvalues"] >= np.array(p) - 1e-9).all()      # q >= p
    print(f"✓ Benjamini-Hochberg rejects {int(bh['reject'].sum())}/4, q-values monotone")


def test_beta_binomial_shrinks():
    bb = rs.beta_binomial_posterior(wins=9, n=10)
    assert bb["lo"] < bb["posterior_mean"] < bb["hi"]
    assert bb["posterior_mean"] < bb["raw_win_rate"]        # shrinks toward 0.5
    assert bb["posterior_mean"] > 0.5
    print(f"✓ Beta-Binomial shrinks 90% -> {bb['posterior_mean']*100:.1f}% "
          f"[{bb['lo']*100:.0f},{bb['hi']*100:.0f}]")


def test_annealer_finds_optimum():
    res = qi.anneal(lambda v: (v[0] - 3.0) ** 2, x0=[0.0], bounds=[(-10.0, 10.0)],
                    maximize=False, steps=4000, seed=0)
    assert abs(res["x"][0] - 3.0) < 0.3, res
    print(f"✓ annealer minimises (x-3)^2 at x={res['x'][0]:.3f} (accept {res['accept_rate']:.2f})")


if __name__ == "__main__":
    test_execution_costs_penalise()
    test_latency_is_adverse()
    test_bootstrap_ci_covers_mean()
    test_permutation_separates()
    test_benjamini_hochberg()
    test_beta_binomial_shrinks()
    test_annealer_finds_optimum()
    print("\n✅ execution + robustness self-checks passed.")
