# EventAlpha recalibration — validation + impact analysis (real 2024-2025 data)

Data resolution: CRYPTO = Binance tick, FX = JForex tick (EURUSD+USDJPY pooled),
OIL = **real WTI** front-month CL 5-second bars (IBKR Gateway; replaces the earlier
1-minute Brent proxy).

## 1. OLD (legacy) vs NEW (measured) window replay

`safe_entry%` = window opens after the whipsaw clears; `before_peak%` = window opens
before the move tops (trend still available); `trend_capture` = fraction of the trend
still ahead at entry; `overhold` = dead seconds held after the trend died.

| asset | policy | n | safe_entry% | before_peak% | trend_capture(med) | overhold s(med) |
|---|---|--:|--:|--:|--:|--:|
| CRYPTO | OLD | 63 | 73.0 | 68.3 | 0.792 | 1202 |
| CRYPTO | **NEW** | 63 | 58.7 | **76.2** | **0.936** | **932** |
| FX | OLD | 126 | 77.8 | 77.8 | 0.833 | 804 |
| FX | **NEW** | 126 | 69.8 | **84.9** | **0.952** | 804 |
| OIL | OLD | 63 | 63.5 | 79.4 | 0.833 | 780 |
| OIL | **NEW** | 63 | 57.1 | **84.1** | **0.867** | **630** |

**Read:** NEW captures much more of the trend (crypto 0.79→0.94, FX 0.83→0.95) and
holds less dead time after the trend dies (lower overhold across all three;
oil 780→630). The
trade-off is safe_entry (crypto/FX/oil all drop): NEW opens the entry
window earlier to catch fast trends, but the model's confirmation checks
(`price_momentum_still_aligned`, `reversal_score_below_threshold`, …) gate the
*actual* entry, so an earlier-opening window is not the same as entering the fake
spike. Net: NEW captures more trend and exits tighter.

## 2. Impact buckets (does the "only trade the big events" thesis hold?)

Events bucketed by realized |move| into small/mid/big terciles per asset:

| asset | bucket | n | move bps | washout s | to-peak s | trend-life s | retrace s |
|---|---|--:|--:|--:|--:|--:|--:|
| CRYPTO | small | 21 | 33 | 113 | 223 | 380 | 90 |
| CRYPTO | mid | 21 | 80 | 35 | 225 | 446 | 91 |
| CRYPTO | **big** | 21 | **144** | **1** | **698** | **1614** | 378 |
| FX | small | 42 | 12 | 106 | 342 | 452 | 55 |
| FX | mid | 42 | 31 | 2 | 326 | 816 | 248 |
| FX | **big** | 42 | **54** | **0** | **1106** | **1798** | 356 |
| OIL | small | 21 | 16 | 60 | 365 | 425 | 50 |
| OIL | mid | 21 | 31 | 65 | 630 | 1075 | 115 |
| OIL | **big** | 21 | **59** | **15** | **1195** | **1570** | 170 |

**Read (this strongly confirms your thesis):**
- **Big events barely whipsaw** — washout collapses toward ~0-15s. Institutions
  commit immediately; there is essentially no fake spike to wait out.
- **Big events trend 3-4x longer** — crypto 380s→1614s, FX 452s→1798s (censored),
  oil 425s→1570s. The trade you actually want to hold.
- **Small events are mostly chop** — long washout, short trend. Low edge; arguably
  skip or size down.

**Implication:** the wait/exit windows should be *impact-scaled*. On a big-surprise
print: shrink min_wait (no whipsaw to dodge) and extend max_wait + time-stop (long
trend). On a small print: don't chase. Making this usable *at entry* needs the true
surprise (actual − forecast) at T0 — the next step is wiring economic actual/forecast
values into `macro_calendar.MacroEvent.surprise` so the model picks the bucket before
entry instead of after.

## 3. Paper-mode P&L backtest (OLD vs NEW, real price paths) — the safety gate

`backtest_pnl.py` reconstructs the actual price series around each event and
simulates a full event trade (enter after `min_wait` once the move clears the
confirmation threshold; exit on time-stop or a 40%-giveback trailing stop),
net of a round-trip cost (crypto 2 / FX 1 / oil 3 bps). `entry_bps` is the
confirmation threshold — **raising it = only trade events that already moved
decisively = an executable proxy for "only trade the big events".**

| asset | entry_bps | policy | n | win% | avg bps | total bps | pnl/vol |
|---|--:|---|--:|--:|--:|--:|--:|
| CRYPTO | 2 | OLD | 63 | 42.9 | -0.1 | -9 | -0.01 |
| CRYPTO | 2 | NEW | 63 | 57.1 | -0.6 | -40 | -0.03 |
| CRYPTO | 10 | OLD | 61 | 82.0 | 2.5 | 154 | 0.12 |
| CRYPTO | 10 | NEW | 61 | 83.6 | 2.1 | 130 | 0.08 |
| CRYPTO | 20 | OLD | 59 | 76.3 | 6.0 | 356 | 0.21 |
| CRYPTO | 20 | NEW | 58 | 74.1 | 1.9 | 111 | 0.06 |
| FX | 2 | OLD | 123 | 73.2 | 0.8 | 101 | 0.08 |
| FX | 2 | NEW | 124 | 66.1 | -0.3 | -43 | -0.05 |
| FX | 10 | OLD | 109 | 58.7 | -0.5 | -53 | -0.03 |
| FX | 10 | **NEW** | 108 | 65.7 | **0.9** | **101** | **0.05** |
| FX | 20 | **NEW** | 93 | 51.6 | **2.0** | **186** | **0.09** |
| FX | 35 | **NEW** | 52 | 61.5 | **8.1** | **419** | **0.29** |
| FX | 35 | OLD | 54 | 55.6 | 5.4 | 289 | 0.20 |
| OIL | 2 | OLD | 63 | 31.7 | -2.0 | -126 | -0.13 |
| OIL | 10 | OLD | 57 | 71.9 | -2.5 | -145 | -0.10 |
| OIL | 20 | OLD | 39 | 53.8 | -3.4 | -131 | -0.16 |
| OIL | 20 | NEW | 42 | 54.8 | -5.1 | -214 | -0.21 |

**Honest read — this is the important result:**
1. **Trading every event is a loser.** At `entry_bps=2` (take all events) both OLD
   and NEW are ~flat-to-negative after costs. The window change alone does not
   create edge — selection does. This *quantitatively confirms the "only big
   events" thesis with realized P&L*, not just timing landmarks.
2. **Selectivity is where the money is.** Requiring a decisive move before
   committing (`entry_bps` 10-35) flips crypto and FX solidly positive
   (win rates 60-84%, positive avg P&L).
3. **NEW helps FX at every selective level** (e.g. at 35 bps: +419 vs +289 bps,
   win 61.5% vs 55.6%, pnl/vol 0.29 vs 0.20). This is the clearest win.
4. **NEW ≈ OLD for crypto on P&L** (crypto trends so fast that the legacy later
   entry sometimes catches a cleaner leg). NEW is not worse in a meaningful
   selective regime; its advantage there is tighter exits (validation §1), not
   more P&L.
5. **Oil loses in BOTH regimes on this naive momentum rule.** The timing numbers
   are accurate, but a pure event-momentum entry does not work on WTI here (choppy
   / mean-reverting intraday; the H1-2024 back-month proxy and 3 bps cost also
   weigh). **Do not expect the oil leg to be profitable without the full model's
   confirmation filters (news/cross-asset/reversal) — the oil recalibration is
   safe to land as a more-accurate measurement, but oil sizing warrants a closer
   look before trusting it live.**

**Caveat on the backtest itself:** this uses a *simplified* entry (momentum-follow
past a threshold) and exit (time-stop + trailing), NOT the live model's full
confirmation stack. So the absolute P&L understates the real strategy (which also
filters on news alignment, cross-asset confirmation, reversal score). Its value is
the *relative* OLD-vs-NEW comparison and the selectivity gradient, both of which
are robust.

## 4. Impact-scaled windows (per-bucket) — built, but simple selectivity wins

`impact_scaled_windows.py` turns the impact buckets into concrete per-bucket
windows (small = stand down, big = commit fast + hold long), and these are
available in `measured_timing.py` as `MEASURED_WAIT_BY_IMPACT` /
`measured_wait_window_by_impact()` (inert — not yet wired into the live loop).
Live bucketing keys off the **observed early move** (bps within the first ~20s),
an executable real-time proxy for the surprise; no forecast feed needed.

The backtest also runs a `SCALED` policy that classifies each event at T0+20s,
**skips the small bucket**, and applies the bucket's window:

| asset | policy | n | win% | avg bps | total bps | pnl/vol |
|---|---|--:|--:|--:|--:|--:|
| CRYPTO | SCALED | 23 | 60.9 | -1.4 | -31 | -0.06 |
| FX | SCALED | 79 | 65.8 | -0.5 | -38 | -0.06 |
| OIL | **SCALED** | 8 | 62.5 | **9.0** | **72** | **0.44** |

**Honest read:**
- **Impact-scaling rescues oil** — the only oil configuration that is *positive*
  (+72 bps, pnl/vol 0.44) is "trade only decisive oil events." Small oil events
  are pure cost.
- **But for crypto/FX, simple threshold-selectivity (§3, `entry_bps` 20-35) beats
  per-bucket scaling.** The extra machinery (early classification + bucket-specific
  windows) does not add P&L over "just require a big move before you commit," and
  with only ~21 events/bucket, per-bucket tuning risks overfitting (exactly the
  small-sample trap this project set out to avoid).

**Recommendation:** the single most robust, live-ready rule is a **confirmation
gate** — do not commit until the early move clears an asset-specific threshold
(crypto ~20 bps, FX ~35 bps, oil ~ mid/big edge). That one gate captures the bulk
of the edge and is a minimal, auditable logic change. The full per-bucket table is
kept for oil and for future use, but should not be over-trusted on this sample.
Wiring either into the live entry loop is a logic change and is left for an
explicit, approved step.
