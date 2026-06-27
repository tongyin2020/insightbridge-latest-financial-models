from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import exp
from typing import Dict, List, Tuple


class MacroRegime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    INFLATION_SHOCK = "inflation_shock"
    GROWTH_SHOCK = "growth_shock"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    CENTRAL_BANK_PIVOT = "central_bank_pivot"
    WAR_SHOCK = "war_shock"
    DOLLAR_SQUEEZE = "dollar_squeeze"
    NEUTRAL = "neutral"


@dataclass
class RegimeInput:
    dxy_momentum: float = 0.0
    us2y_yield_momentum: float = 0.0
    us10y_yield_momentum: float = 0.0
    breakeven_inflation_momentum: float = 0.0
    gold_momentum: float = 0.0
    oil_momentum: float = 0.0
    equity_momentum: float = 0.0
    vix_momentum: float = 0.0
    credit_spread_momentum: float = 0.0
    btc_momentum: float = 0.0
    policy_hawkishness: float = 0.0
    geopolitical_tension: float = 0.0
    liquidity_stress: float = 0.0


@dataclass
class RegimeOutput:
    primary: MacroRegime
    probabilities: Dict[MacroRegime, float]
    explanation: List[str]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


def infer_macro_regime(x: RegimeInput) -> RegimeOutput:
    """Rule-plus-probability regime engine.

    This is intentionally interpretable. It can later be replaced by HMM,
    Bayesian switching, or a neural state-space model after sufficient data.
    Inputs should be standardized scores, roughly -3 to +3.
    """
    raw = {
        MacroRegime.RISK_ON: 1.1*x.equity_momentum + 0.8*x.btc_momentum - 0.7*x.vix_momentum - 0.5*x.credit_spread_momentum,
        MacroRegime.RISK_OFF: 1.1*x.vix_momentum + 0.8*x.gold_momentum + 0.7*x.credit_spread_momentum - 0.8*x.equity_momentum,
        MacroRegime.INFLATION_SHOCK: 1.0*x.breakeven_inflation_momentum + 0.8*x.oil_momentum + 0.7*x.us2y_yield_momentum + 0.5*x.policy_hawkishness,
        MacroRegime.GROWTH_SHOCK: -1.0*x.equity_momentum + 0.8*x.credit_spread_momentum - 0.6*x.us10y_yield_momentum + 0.4*x.vix_momentum,
        MacroRegime.LIQUIDITY_CRISIS: 1.2*x.liquidity_stress + 0.7*x.dxy_momentum + 0.7*x.vix_momentum + 0.6*x.credit_spread_momentum,
        MacroRegime.CENTRAL_BANK_PIVOT: -0.9*x.us2y_yield_momentum - 0.6*x.policy_hawkishness + 0.4*x.equity_momentum,
        MacroRegime.WAR_SHOCK: 1.2*x.geopolitical_tension + 0.7*x.oil_momentum + 0.6*x.gold_momentum + 0.3*x.vix_momentum,
        MacroRegime.DOLLAR_SQUEEZE: 1.2*x.dxy_momentum + 0.7*x.us2y_yield_momentum + 0.4*x.vix_momentum - 0.3*x.equity_momentum,
        MacroRegime.NEUTRAL: 0.2,
    }
    pos = {k: _sigmoid(v) for k, v in raw.items()}
    total = sum(pos.values()) or 1.0
    probs = {k: v / total for k, v in pos.items()}
    primary = max(probs, key=probs.get)
    explanation = [f"{k.value}={v:.2f}" for k, v in sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:4]]
    return RegimeOutput(primary=primary, probabilities=probs, explanation=explanation)
