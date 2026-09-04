# GDELT real-news-tone directional test

Real GDELT average news tone (+/-3h around each release, 15-minute resolution) attached to **50/63** 2024-2025 NFP/CPI/FOMC events (topics: inflation / unemployment / federal reserve). This is a price-INDEPENDENT feed, so it can genuinely test whether news mood carries directional information -- unlike the price-collinear proxy used earlier.

`tone_change` = mean tone after the release minus mean tone before. `hit_%` = share of events where the sign of `tone_change` matches the sign of the realised price move (early = +5min, net = over the 30-min horizon). 50% and corr~0 mean no directional signal.

| asset | n | tone->early_hit_% | tone~early_corr | tone->net_hit_% | tone~net_corr |
| --- | --- | --- | --- | --- | --- |
| CRYPTO | 50 | 54.0 | 0.082 | 54.0 | 0.105 |
| FX | 100 | 47.0 | 0.042 | 52.0 | 0.064 |
| OIL | 47 | 63.8 | 0.042 | 60.0 | 0.223 |
| ALL | 197 | 52.8 | 0.054 | 54.5 | 0.105 |

## Verdict

- Read the ALL row: hit-rate near 50% and |corr| near 0 mean GDELT topic tone does **not** predict the direction of the macro-event move -- news *positivity* is not the same as the *surprise vs expectations* that moves price, so it cannot replace a real consensus-forecast surprise.
- This is why the full-stack replay's news leg is only a risk/context input, not a directional edge. Attaching real tone does not change that; a true *surprise* feed (actual-vs-forecast) remains the missing piece.
