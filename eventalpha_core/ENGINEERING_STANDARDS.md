# EventAlpha Engineering Standards (operational)

These are the concrete, enforced versions of the standards in the Developer
Edition spec. Two are wired into the code today; the rest are the target.

## 1. Selectivity gate (the one data-proven alpha lever)

The 2024-2025 P&L study showed the edge is in **selectivity**: trading every
event is flat/negative, while committing only to decisive ("mid"/"big") events
and standing down on "small" ones turns crypto/FX positive
(`eventalpha_intraday_study/backtest_pnl.py`, `reports/IMPACT_SCALED_WINDOWS.md`).

That rule is now available inside the decision chain:

- `EventAlphaBrain(..., selectivity_enabled=False)` — **off by default**, so the
  chain is byte-for-byte unchanged unless a caller opts in (paper first).
- Input: `MarketState.early_move_bps` — the observed early post-event reaction
  magnitude (bps), the executable real-time proxy for the surprise. Adapters can
  also pass it via `state.raw["early_move_bps"]`.
- When enabled: `impact_bucket == "small"` → stand down (action `WATCH`);
  `mid`/`big` → adopt the measured impact-scaled window (`advanced.measured_timing`).
- Every decision records `impact_bucket`, `early_move_bps`, `selectivity_enabled`,
  and `selectivity_applied` in `EventDecision.metadata` for audit (even when off).
- Enable in the paper runner with `--selectivity` or `EVENTALPHA_SELECTIVITY=1`.

The same gate is also wired into the **live** IBKR path
(`execution_framework/event_right_side_engine.py`), again **off by default**:
`RightSideEventEngine(selectivity_enabled=False)`, enabled via
`RightSidePipeline(selectivity_enabled=True)` or `EVENTALPHA_SELECTIVITY=1`. There
the early move is measured from the trigger-bar close; on a confirmed breakout a
`small`-impact event is stood down (`HOLD`), and `impact_bucket` / `early_move_bps`
are attached to the signal for audit. Only crypto/FX symbols have measured edges;
INDEX/TREASURY/RATES no-op.

Guards (deterministic, data-free): `eventalpha_core/test_selectivity_gate.py`
(brain path) and `execution_framework/test_selectivity_live.py` (live engine).

## 2. Decision logging (every decision, joinable to realized PnL)

`eventalpha_core/decision_log.py` writes one JSONL row per decision with
probabilities, thresholds, confidence, memory edge, regime, impact bucket, and
the action — then a linked `outcome` row (realized PnL / MFE / MAE / hold) when
the trade closes. Wired into `run_eventalpha_paper.py`
(`reports/eventalpha_decisions.jsonl`).

## 3. Replay-on-change + metrics regression gate

Standard: **replay every change against the 2024-2025 dataset before deploy** and
**compare against previous validation metrics**.

- `eventalpha_intraday_study/metrics_baseline.py` holds the committed baseline of
  the headline metrics and a direction-aware `compare_metrics()` (adverse move
  beyond `max(abs_tol, base*rel_tol)` = regression).
- Guard: `eventalpha_intraday_study/test_metrics_regression.py` (data-free).
- On a real change: re-run the study on the tick dataset, collect the same keys,
  call `compare_metrics(load_baseline(), current, SPECS)`; a non-empty result
  blocks the change. Update the baseline only deliberately via `save_baseline()`.

## Running the guards

```
python3 eventalpha_core/test_selectivity_gate.py
python3 execution_framework/test_selectivity_live.py
python3 eventalpha_intraday_study/test_metrics_regression.py
python3 execution_framework/test_crypto_spot.py
python3 execution_framework/test_pre_event.py
python3 execution_framework/test_pipeline_dryrun.py
```
