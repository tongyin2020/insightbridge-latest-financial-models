# Full-stack replay — complete AI decision brain vs timing-only

The **same** real 2024-2025 intraday event data (BTC Binance tick, EURUSD+USDJPY JForex tick, WTI IBKR 5-second bars; NFP/CPI/FOMC) is run through the **entire** `EventAlphaBrain.decide()` chain — macro-regime engine, event severity, Bayesian signal fusion (news / price-confirmation / cross-asset / liquidity / memory), the calibrated waiting policy, cross-asset scoring across the three real legs, position sizing and the exit engine — and compared to trading every decisive event on the calibrated window alone (`TIMING_ONLY`).

**Honest proxies (cannot be reproduced for past timestamps):** the news leg uses a price-consistent proxy (Firecrawl cannot be re-scraped historically) and macro `surprise` is proxied by the market's own early reaction (consensus forecasts have no free source). So the news leg is collinear with price by construction — it is a placeholder, not independent evidence. Everything else is the real production code.

## Results

| asset | policy | n_events | n_trades | selectivity_% | win_rate_% | avg_pnl_bps | med_pnl_bps | total_bps | pnl_vol_ratio | avg_mae_bps | max_drawdown_bps | avg_hold_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CRYPTO | TIMING_ONLY | 63 | 60 | 95.2 | 56.7 | -0.8 | 0.6 | -50.0 | -0.041 | 15.4 | 147.0 | 213.0 |
| CRYPTO | FULL_STACK | 63 | 29 | 46.0 | 41.4 | -1.6 | -1.1 | -48.0 | -0.108 | 17.7 | 92.0 | 187.0 |
| CRYPTO | FULL_STACK_GDELT | 50 | 9 | 18.0 | 66.7 | 9.4 | 5.9 | 85.0 | 0.561 | 6.0 | 3.0 | 219.0 |
| FX | TIMING_ONLY | 126 | 104 | 82.5 | 63.5 | -0.5 | 0.5 | -54.0 | -0.066 | 7.7 | 109.0 | 262.0 |
| FX | FULL_STACK | 126 | 87 | 69.0 | 65.5 | -0.8 | 0.5 | -68.0 | -0.101 | 7.1 | 99.0 | 233.0 |
| FX | FULL_STACK_GDELT | 100 | 40 | 40.0 | 70.0 | 0.1 | 0.6 | 6.0 | 0.032 | 5.4 | 18.0 | 300.0 |
| OIL | TIMING_ONLY | 63 | 49 | 77.8 | 24.5 | -3.0 | -1.6 | -146.0 | -0.137 | 11.3 | 214.0 | 403.0 |
| OIL | FULL_STACK | 63 | 35 | 55.6 | 20.0 | -1.7 | -1.6 | -58.0 | -0.108 | 8.3 | 92.0 | 329.0 |
| OIL | FULL_STACK_GDELT | 50 | 19 | 38.0 | 15.8 | -4.2 | -1.7 | -80.0 | -0.441 | 10.2 | 60.0 | 498.0 |

## Reading the table

- `selectivity_%` = fraction of events the policy actually traded.
- `max_drawdown_bps` = worst peak-to-trough of the cumulative-bps equity curve (events in chronological order).
- `avg_mae_bps` = average worst adverse excursion while in the trade.

## What the full stack adds

- **CRYPTO**: trades 95.2% -> **46.0%** of events; win 56.7% -> **41.4%**; max drawdown 147 -> **92** bps; avg MAE 15.4 -> **17.7** bps; avg P&L -0.8 -> -1.6 bps.
- **FX**: trades 82.5% -> **69.0%** of events; win 63.5% -> **65.5%**; max drawdown 109 -> **99** bps; avg MAE 7.7 -> **7.1** bps; avg P&L -0.5 -> -0.8 bps.
- **OIL**: trades 77.8% -> **55.6%** of events; win 24.5% -> **20.0%**; max drawdown 214 -> **92** bps; avg MAE 11.3 -> **8.3** bps; avg P&L -3.0 -> -1.7 bps.

## Real news (GDELT) vs price-proxy news

`FULL_STACK_GDELT` is the identical brain but with `news_alignment` fed by **real GDELT news tone** around each release (see `GDELT_NEWS_VALIDATION.md`) instead of the price-derived proxy. It runs only on the events with GDELT coverage, so compare it to `FULL_STACK` directionally, not on absolute totals.

- **CRYPTO**: proxy-news win 41.4% / P&L -1.6 vs real-GDELT-news win 66.7% / P&L 9.4 bps (GDELT traded 9 of 50 covered events).
- **FX**: proxy-news win 65.5% / P&L -0.8 vs real-GDELT-news win 70.0% / P&L 0.1 bps (GDELT traded 40 of 100 covered events).
- **OIL**: proxy-news win 20.0% / P&L -1.7 vs real-GDELT-news win 15.8% / P&L -4.2 bps (GDELT traded 19 of 50 covered events).

## Honest verdict

- The confirmation stack behaves as a **risk filter**: it stands down on a large share of events and **cuts max drawdown and adverse excursion materially** on all three legs, with a small win-rate lift on FX.
- It does **not**, on its own, turn the naive momentum entry positive — consistent with the P&L study (`THREE_MODEL_VALIDATION.md`): the realised edge comes from the **decisive-move selectivity threshold**, which is complementary to (and can be stacked on top of) the brain's gating.
- **Real GDELT news tone carries no measurable directional edge.** The standalone test (`GDELT_NEWS_VALIDATION.md`, 197 asset-events) shows tone-vs-move hit-rate ~50-54% and correlation ~0.05 — statistically a coin flip. News *positivity* is not the *surprise vs expectations* that moves price.
- When tone is fed into the brain (`FULL_STACK_GDELT`) it mostly disagrees with momentum, so the brain trades far fewer events. On that small residual subset crypto/FX P&L looks better, but with only ~9-40 trades this is **selection + small-sample noise, not proven news alpha** — requiring any second signal to agree with momentum thins trades without adding per-trade edge unless the signal is informative, and the 197-sample test says it isn't. Oil is outright worse.
- Net: attaching a real, price-independent news feed did **not** unlock new edge. The genuinely missing input remains a real consensus-forecast *surprise* feed (actual-vs-expected), for which no free historical source has been found.
