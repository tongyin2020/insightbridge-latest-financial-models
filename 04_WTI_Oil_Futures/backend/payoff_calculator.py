"""
WTI Trading Platform - Options Payoff Diagram Calculator
Generates payoff curves for strategy visualization at expiry.
"""
import math
from typing import Dict, List


def calculate_payoff(
    strategy_type: str,
    underlying_price: float,
    expiry_days: int = 30,
    risk_free_rate: float = 0.05,
    iv: float = 0.25,
    price_range_pct: float = 15.0,
    num_points: int = 60,
) -> Dict:
    """
    Calculate payoff diagram data for a given strategy.
    Returns price points and P&L at each point.
    """
    strike = round(underlying_price)
    min_price = underlying_price * (1 - price_range_pct / 100)
    max_price = underlying_price * (1 + price_range_pct / 100)
    step = (max_price - min_price) / num_points

    prices = [round(min_price + i * step, 2) for i in range(num_points + 1)]
    T = expiry_days / 365

    # Black-Scholes premiums at entry
    def bs_call(S, K, T_val, r, sigma):
        if T_val <= 0 or sigma <= 0:
            return max(0, S - K)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T_val) / (sigma * math.sqrt(T_val))
        d2 = d1 - sigma * math.sqrt(T_val)
        from scipy.stats import norm
        return S * norm.cdf(d1) - K * math.exp(-r * T_val) * norm.cdf(d2)

    def bs_put(S, K, T_val, r, sigma):
        if T_val <= 0 or sigma <= 0:
            return max(0, K - S)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T_val) / (sigma * math.sqrt(T_val))
        d2 = d1 - sigma * math.sqrt(T_val)
        from scipy.stats import norm
        return K * math.exp(-r * T_val) * norm.cdf(-d2) - S * norm.cdf(-d1)

    payoff_at_expiry = []
    payoff_now = []

    if strategy_type == "straddle":
        call_premium = bs_call(underlying_price, strike, T, risk_free_rate, iv)
        put_premium = bs_put(underlying_price, strike, T, risk_free_rate, iv)
        total_cost = (call_premium + put_premium) * 1000
        be_lower = strike - call_premium - put_premium
        be_upper = strike + call_premium + put_premium

        for p in prices:
            expiry_pnl = (max(0, p - strike) + max(0, strike - p)) * 1000 - total_cost
            now_pnl = (bs_call(p, strike, T, risk_free_rate, iv) + bs_put(p, strike, T, risk_free_rate, iv)) * 1000 - total_cost
            payoff_at_expiry.append(round(expiry_pnl, 2))
            payoff_now.append(round(now_pnl, 2))

        return _build_result(strategy_type, "Straddle", prices, payoff_at_expiry, payoff_now,
                             total_cost, None, [be_lower, be_upper], strike, underlying_price)

    elif strategy_type == "strangle":
        call_strike = round(underlying_price * 1.03, 2)
        put_strike = round(underlying_price * 0.97, 2)
        call_prem = bs_call(underlying_price, call_strike, T, risk_free_rate, iv)
        put_prem = bs_put(underlying_price, put_strike, T, risk_free_rate, iv)
        total_cost = (call_prem + put_prem) * 1000

        for p in prices:
            expiry_pnl = (max(0, p - call_strike) + max(0, put_strike - p)) * 1000 - total_cost
            now_pnl = (bs_call(p, call_strike, T, risk_free_rate, iv) + bs_put(p, put_strike, T, risk_free_rate, iv)) * 1000 - total_cost
            payoff_at_expiry.append(round(expiry_pnl, 2))
            payoff_now.append(round(now_pnl, 2))

        return _build_result(strategy_type, "Strangle", prices, payoff_at_expiry, payoff_now,
                             total_cost, None, [put_strike - call_prem - put_prem, call_strike + call_prem + put_prem],
                             strike, underlying_price)

    elif strategy_type == "iron_condor":
        put_buy = round(underlying_price * 0.95)
        put_sell = round(underlying_price * 0.97)
        call_sell = round(underlying_price * 1.03)
        call_buy = round(underlying_price * 1.05)

        credit = (bs_put(underlying_price, put_sell, T, risk_free_rate, iv)
                  - bs_put(underlying_price, put_buy, T, risk_free_rate, iv)
                  + bs_call(underlying_price, call_sell, T, risk_free_rate, iv)
                  - bs_call(underlying_price, call_buy, T, risk_free_rate, iv)) * 1000

        for p in prices:
            put_spread_exp = max(0, put_sell - p) - max(0, put_buy - p)
            call_spread_exp = max(0, p - call_sell) - max(0, p - call_buy)
            expiry_pnl = credit - (put_spread_exp + call_spread_exp) * 1000
            payoff_at_expiry.append(round(expiry_pnl, 2))
            now_val = (bs_put(p, put_sell, T, risk_free_rate, iv) - bs_put(p, put_buy, T, risk_free_rate, iv)
                       + bs_call(p, call_sell, T, risk_free_rate, iv) - bs_call(p, call_buy, T, risk_free_rate, iv)) * 1000
            payoff_now.append(round(credit - now_val, 2))

        max_loss = max(call_buy - call_sell, put_sell - put_buy) * 1000 - credit
        return _build_result(strategy_type, "Iron Condor", prices, payoff_at_expiry, payoff_now,
                             -credit, max_loss, [put_sell - credit/1000, call_sell + credit/1000],
                             strike, underlying_price)

    elif strategy_type == "butterfly":
        lower = strike - 2.5
        upper = strike + 2.5
        cost = (bs_call(underlying_price, lower, T, risk_free_rate, iv)
                - 2 * bs_call(underlying_price, strike, T, risk_free_rate, iv)
                + bs_call(underlying_price, upper, T, risk_free_rate, iv)) * 1000

        for p in prices:
            expiry_val = (max(0, p - lower) - 2 * max(0, p - strike) + max(0, p - upper)) * 1000
            expiry_pnl = expiry_val - cost
            payoff_at_expiry.append(round(expiry_pnl, 2))
            now_val = (bs_call(p, lower, T, risk_free_rate, iv) - 2 * bs_call(p, strike, T, risk_free_rate, iv) + bs_call(p, upper, T, risk_free_rate, iv)) * 1000
            payoff_now.append(round(now_val - cost, 2))

        return _build_result(strategy_type, "Butterfly", prices, payoff_at_expiry, payoff_now,
                             cost, cost, [lower + cost/1000, upper - cost/1000], strike, underlying_price)

    elif strategy_type == "calendar_spread":
        T_near = 30 / 365
        T_far = 60 / 365
        near_prem = bs_call(underlying_price, strike, T_near, risk_free_rate, iv)
        far_prem = bs_call(underlying_price, strike, T_far, risk_free_rate, iv)
        cost = (far_prem - near_prem) * 1000

        for p in prices:
            near_val = max(0, p - strike)
            far_val = bs_call(p, strike, T_far - T_near, risk_free_rate, iv)
            expiry_pnl = (far_val - near_val) * 1000 - cost
            payoff_at_expiry.append(round(expiry_pnl, 2))
            payoff_now.append(round(expiry_pnl * 0.6, 2))

        return _build_result(strategy_type, "Calendar Spread", prices, payoff_at_expiry, payoff_now,
                             cost, cost, [strike - 1.5, strike + 1.5], strike, underlying_price)

    elif strategy_type == "ratio_spread":
        short_strike = round(underlying_price * 1.05, 2)
        long_prem = bs_call(underlying_price, strike, T, risk_free_rate, iv)
        short_prem = bs_call(underlying_price, short_strike, T, risk_free_rate, iv)
        cost = (long_prem - 2 * short_prem) * 1000

        for p in prices:
            expiry_val = (max(0, p - strike) - 2 * max(0, p - short_strike)) * 1000
            expiry_pnl = expiry_val - cost
            payoff_at_expiry.append(round(expiry_pnl, 2))
            now_val = (bs_call(p, strike, T, risk_free_rate, iv) - 2 * bs_call(p, short_strike, T, risk_free_rate, iv)) * 1000
            payoff_now.append(round(now_val - cost, 2))

        return _build_result(strategy_type, "Ratio Spread 1x2", prices, payoff_at_expiry, payoff_now,
                             cost, None, [strike + cost/1000, 2*short_strike - strike + cost/1000],
                             strike, underlying_price)

    return {"error": "Unknown strategy"}


def _build_result(strategy_type, name, prices, payoff_expiry, payoff_now, cost, max_loss, breakevens, strike, spot):
    max_profit_exp = max(payoff_expiry)
    max_loss_exp = min(payoff_expiry)
    return {
        "strategy": strategy_type,
        "name": name,
        "spot_price": spot,
        "strike": strike,
        "cost": round(cost, 2),
        "max_profit": round(max_profit_exp, 2),
        "max_loss": round(max_loss_exp, 2),
        "breakeven_points": [round(b, 2) for b in breakevens],
        "data": [
            {"price": p, "expiry_pnl": pe, "current_pnl": pn}
            for p, pe, pn in zip(prices, payoff_expiry, payoff_now)
        ],
    }
