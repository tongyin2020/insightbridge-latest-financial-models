import math
import logging
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    """Black-Litterman portfolio optimization engine for bond/rate assets."""

    ASSETS = [
        {"symbol": "UST_2Y", "name": "2-Year Treasury", "category": "short"},
        {"symbol": "UST_5Y", "name": "5-Year Treasury", "category": "medium"},
        {"symbol": "UST_10Y", "name": "10-Year Treasury", "category": "long"},
        {"symbol": "UST_30Y", "name": "30-Year Treasury", "category": "long"},
        {"symbol": "TIPS", "name": "TIPS (Inflation Protected)", "category": "tips"},
        {"symbol": "IG_CORP", "name": "Investment Grade Corporate", "category": "credit"},
        {"symbol": "HY_CORP", "name": "High Yield Corporate", "category": "credit"},
        {"symbol": "MBS", "name": "Mortgage-Backed Securities", "category": "mbs"},
    ]

    # Historical expected returns (annualized)
    EXPECTED_RETURNS = np.array([0.042, 0.040, 0.043, 0.045, 0.035, 0.055, 0.072, 0.048])

    # Historical covariance matrix (annualized)
    COV_MATRIX = np.array([
        [0.0012, 0.0015, 0.0018, 0.0020, 0.0010, 0.0008, 0.0005, 0.0011],
        [0.0015, 0.0028, 0.0035, 0.0040, 0.0020, 0.0015, 0.0008, 0.0022],
        [0.0018, 0.0035, 0.0055, 0.0065, 0.0030, 0.0022, 0.0012, 0.0035],
        [0.0020, 0.0040, 0.0065, 0.0090, 0.0038, 0.0028, 0.0015, 0.0045],
        [0.0010, 0.0020, 0.0030, 0.0038, 0.0040, 0.0018, 0.0010, 0.0025],
        [0.0008, 0.0015, 0.0022, 0.0028, 0.0018, 0.0035, 0.0025, 0.0020],
        [0.0005, 0.0008, 0.0012, 0.0015, 0.0010, 0.0025, 0.0060, 0.0015],
        [0.0011, 0.0022, 0.0035, 0.0045, 0.0025, 0.0020, 0.0015, 0.0042],
    ])

    # Market cap weights (equilibrium)
    MARKET_WEIGHTS = np.array([0.20, 0.15, 0.20, 0.10, 0.08, 0.12, 0.05, 0.10])

    def __init__(self, db):
        self.db = db

    async def optimize(self, views: Optional[List[Dict]] = None,
                       risk_aversion: float = 2.5, tau: float = 0.05,
                       constraints: Optional[Dict] = None) -> Dict[str, Any]:
        """Run Black-Litterman optimization with optional investor views."""
        n = len(self.ASSETS)
        Sigma = self.COV_MATRIX
        w_mkt = self.MARKET_WEIGHTS

        # Step 1: Implied equilibrium returns (pi = delta * Sigma * w_mkt)
        pi = risk_aversion * Sigma @ w_mkt

        if views and len(views) > 0:
            # Step 2: Build P (pick matrix) and Q (view returns) and Omega
            P, Q, confidence = self._build_view_matrices(views, n)
            if P is not None and len(Q) > 0:
                Omega = np.diag(1.0 / np.array(confidence)) * tau
                # BL formula: E[R] = [(tau*Sigma)^-1 + P'*Omega^-1*P]^-1 * [(tau*Sigma)^-1*pi + P'*Omega^-1*Q]
                tau_Sigma_inv = np.linalg.inv(tau * Sigma)
                Omega_inv = np.linalg.inv(Omega)
                M = np.linalg.inv(tau_Sigma_inv + P.T @ Omega_inv @ P)
                bl_returns = M @ (tau_Sigma_inv @ pi + P.T @ Omega_inv @ Q)
            else:
                bl_returns = pi
        else:
            bl_returns = pi

        # Step 3: Optimal weights (w* = (delta * Sigma)^-1 * bl_returns)
        optimal_weights = np.linalg.inv(risk_aversion * Sigma) @ bl_returns
        optimal_weights = self._apply_constraints(optimal_weights, constraints)
        optimal_weights = optimal_weights / np.sum(optimal_weights)

        # Min variance portfolio
        ones = np.ones(n)
        Sigma_inv = np.linalg.inv(Sigma)
        mv_weights = Sigma_inv @ ones / (ones @ Sigma_inv @ ones)

        # Max Sharpe portfolio
        rf = 0.04
        excess = bl_returns - rf
        ms_weights = Sigma_inv @ excess / (ones @ Sigma_inv @ excess)
        ms_weights = self._apply_constraints(ms_weights, constraints)
        ms_weights = ms_weights / np.sum(ms_weights)

        # Efficient frontier
        frontier = self._compute_efficient_frontier(bl_returns, Sigma, rf)

        # Portfolio metrics
        opt_ret = float(optimal_weights @ bl_returns)
        opt_vol = float(np.sqrt(optimal_weights @ Sigma @ optimal_weights))
        opt_sharpe = (opt_ret - rf) / opt_vol if opt_vol > 0 else 0

        mv_ret = float(mv_weights @ bl_returns)
        mv_vol = float(np.sqrt(mv_weights @ Sigma @ mv_weights))

        ms_ret = float(ms_weights @ bl_returns)
        ms_vol = float(np.sqrt(ms_weights @ Sigma @ ms_weights))
        ms_sharpe = (ms_ret - rf) / ms_vol if ms_vol > 0 else 0

        allocations = []
        for i, asset in enumerate(self.ASSETS):
            allocations.append({
                "symbol": asset["symbol"],
                "name": asset["name"],
                "category": asset["category"],
                "optimal_weight": round(float(optimal_weights[i]) * 100, 2),
                "market_weight": round(float(w_mkt[i]) * 100, 2),
                "mv_weight": round(float(mv_weights[i]) * 100, 2),
                "ms_weight": round(float(ms_weights[i]) * 100, 2),
                "expected_return": round(float(bl_returns[i]) * 100, 3),
                "volatility": round(float(np.sqrt(Sigma[i, i])) * 100, 2),
            })

        return {
            "allocations": allocations,
            "optimal_portfolio": {
                "return": round(opt_ret * 100, 3),
                "volatility": round(opt_vol * 100, 3),
                "sharpe": round(opt_sharpe, 3),
            },
            "min_variance": {
                "return": round(mv_ret * 100, 3),
                "volatility": round(mv_vol * 100, 3),
                "weights": [round(float(w) * 100, 2) for w in mv_weights],
            },
            "max_sharpe": {
                "return": round(ms_ret * 100, 3),
                "volatility": round(ms_vol * 100, 3),
                "sharpe": round(ms_sharpe, 3),
                "weights": [round(float(w) * 100, 2) for w in ms_weights],
            },
            "efficient_frontier": frontier,
            "views_applied": len(views) if views else 0,
            "risk_aversion": risk_aversion,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _build_view_matrices(self, views, n):
        """Build P, Q, confidence matrices from user views."""
        valid = []
        asset_idx = {a["symbol"]: i for i, a in enumerate(self.ASSETS)}
        for v in views:
            idx = asset_idx.get(v.get("asset"))
            if idx is not None and "return_view" in v:
                valid.append((idx, v["return_view"] / 100.0, v.get("confidence", 0.5)))

        if not valid:
            return None, None, None

        P = np.zeros((len(valid), n))
        Q = np.zeros(len(valid))
        conf = []
        for i, (idx, ret, c) in enumerate(valid):
            P[i, idx] = 1.0
            Q[i] = ret
            conf.append(max(0.1, min(c, 1.0)))
        return P, Q, conf

    def _apply_constraints(self, weights, constraints):
        """Apply min/max weight constraints."""
        w = weights.copy()
        if constraints:
            min_w = constraints.get("min_weight", -0.1)
            max_w = constraints.get("max_weight", 0.5)
            w = np.clip(w, min_w, max_w)
        else:
            w = np.clip(w, -0.05, 0.5)
        return w

    def _compute_efficient_frontier(self, returns, cov, rf, points=25):
        """Compute efficient frontier points."""
        n = len(returns)
        frontier = []
        ones = np.ones(n)
        Sigma_inv = np.linalg.inv(cov)

        min_ret = float(np.min(returns)) * 0.5
        max_ret = float(np.max(returns)) * 1.5

        for target_ret in np.linspace(min_ret, max_ret, points):
            try:
                # Solve for min variance at target return
                A = ones @ Sigma_inv @ ones
                B = ones @ Sigma_inv @ returns
                C = returns @ Sigma_inv @ returns
                det = A * C - B * B
                if det <= 0:
                    continue
                lam = (C - target_ret * B) / det
                gam = (target_ret * A - B) / det
                w = Sigma_inv @ (lam * ones + gam * returns)
                vol = float(np.sqrt(w @ cov @ w))
                ret = float(w @ returns)
                sharpe = (ret - rf) / vol if vol > 0 else 0
                frontier.append({
                    "return": round(ret * 100, 3),
                    "volatility": round(vol * 100, 3),
                    "sharpe": round(sharpe, 3),
                })
            except Exception:
                continue
        return frontier
