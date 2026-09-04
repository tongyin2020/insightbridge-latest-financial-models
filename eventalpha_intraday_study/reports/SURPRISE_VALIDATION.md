# Real macro-surprise directional test (MQL5 consensus)

Real consensus forecasts pulled from the MQL5 historical calendar for **44/47** 2024-2025 NFP/CPI releases (NFP: 23 releases, CPI: 21 releases). `surprise = actual - forecast` is now a genuine, price-independent input (no longer the circular early-reaction proxy). FOMC is excluded: MQL5 carries no consensus for the rate decision, and the FOMC surprise lives in the statement/dot-plot rather than the rate number.

Correlation of real surprise vs the realised price move (early = +5min, net = 30-min horizon). Pearson and Spearman are both shown; Spearman/sign are robust to the occasional bad forecast value in the free feed.

| asset | n | pearson_early | spearman_early | pearson_net | spearman_net |
| --- | --- | --- | --- | --- | --- |
| CRYPTO | 44 | -0.177 | -0.21 | -0.157 | -0.211 |
| FX | 88 | 0.434 | 0.497 | 0.349 | 0.393 |
| OIL | 44 | 0.024 | -0.105 | 0.26 | 0.146 |

FX moves are oriented to **USD strength** (EUR/USD flipped) so the same USD shock reads consistently across both pairs; without this, pooling the two opposite-facing pairs cancels the signal.

## Does the direction translate into P&L?

Same entry window / exit rules as the timing study, on the NFP/CPI events that have a real consensus. **timing** takes the direction of the market's own early move (what the calibrated system does today); **directed** takes the sign implied by the real surprise under fixed economic priors (hot surprise -> long USD / short crypto / long oil -- *not* fitted to P&L). Costs included.

| asset | n | timing_win_% | timing_avg_bps | timing_pnl_vol | directed_win_% | directed_avg_bps | directed_pnl_vol |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRYPTO | 42 | 69.0 | 6.8 | 0.456 | 64.3 | -2.1 | -0.075 |
| FX | 84 | 67.9 | 0.7 | 0.075 | 67.9 | -0.0 | -0.006 |
| OIL | 40 | 32.5 | -0.1 | -0.012 | 30.0 | -0.2 | -0.017 |

## Verdict

1. **Real macro surprise carries genuine directional information** -- most clearly for FX/USD (Spearman ~0.5), and in the economically-expected sign for crypto (risk-off, negative) and oil (demand, positive on the net horizon). This is qualitatively different from GDELT news tone, which was a coin flip (~50%, corr ~0). So the input we spent the project chasing is **real** -- the consensus forecast does contain signal.

2. **But it adds no tradable edge on top of the calibrated timing system.** Trading the surprise-implied direction (`directed`) is *worse* than simply following the market's own early move (`timing`) on every asset (crypto +6.8 vs -2.1 bps, FX +0.7 vs ~0, oil both ~0). The reason is mechanical: by the entry window (30-60s after the release) the market has **already priced the surprise into the early move**, so the realised price reaction is a fresher, more complete version of the same information. When the surprise sign and the early-move sign disagree, price (which already happened) wins.

3. **This retroactively validates the system's design.** EventAlpha already uses the market's early-move magnitude as an executable, real-time proxy for the surprise (see the note in `measured_timing.py`). This test confirms that proxy is not a compromise: paying for a consensus-forecast feed would not improve entries, because price prices the surprise faster than any feed can deliver it. The honest recommendation is to **not** buy a calendar/forecast feed for entry timing.

Data caveat: the free MQL5 feed occasionally stores a wrong forecast (e.g. NFP 2024-01 forecast = 1K, tooltip-confirmed as MQL5's own value); sign/rank stats and the sign-only directed policy are used precisely so a few such magnitude glitches do not drive the conclusion.
