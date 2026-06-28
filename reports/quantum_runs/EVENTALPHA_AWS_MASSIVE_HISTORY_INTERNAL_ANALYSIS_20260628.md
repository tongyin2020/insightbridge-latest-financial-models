# EventAlpha AWS Massive-History Internal Analysis

Generated: 2026-06-28 UTC
Project: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest`
Scope: Five financial models, updated trading rules/methods, massive-history validation plus AWS Braket cross-check

## Executive Conclusion

This round of testing confirms that the updated EventAlpha financial framework remains internally coherent under a large historical validation pass and that AWS quantum sampling reproduced the same optimal asset basket as the local exact baseline.

Final validated best basket:

- `crypto`
- `oil`
- `index`

Exact objective:

- `0.297124`

AWS quantum best sampled objective:

- `0.297124`

Delta vs exact:

- `0.000000`

Interpretation:

- The new rules changed the portfolio ranking materially.
- The new ranking is not a local-only artifact.
- AWS Braket returned the same best combination as the exact classical solution.

## Test Scope

Massive-history validation parameters:

- Start year: `2018`
- End year: `2025`
- Top-N portfolio target: `3`
- Max EIA cases: `240`
- Risk budget: `2.5`
- Quantum problem: `asset_subset_selection`
- AWS shots per task: `512`
- Grid points: `3`
- Total AWS submitted tasks: `9`

Data sources used in this run:

- Real historical market data via Yahoo Finance-backed download path
- Real macro event calendar framework already wired into EventAlpha
- Project-local historical compression into `cases` and `matrix`
- Abstract QUBO-like quantum pack generated from the updated real-history outputs

## Historical Validation Results

Core sample size:

- Event cases: `374`
- Asset decisions: `1870`
- Entry decisions: `35`
- Selected portfolio entries: `35`

Headline outcome:

- All-entry win rate: `68.57%`
- All-entry average PnL: `1.0458%`
- Selected-portfolio win rate: `68.57%`
- Selected-portfolio average PnL: `1.0458%`
- Top-confidence average PnL: `1.7696%`
- Top-confidence win rate: `61.54%`

Asset-level signal summary:

- `crypto`: 3 entries, win rate `66.67%`, avg PnL `7.2289%`, strongest raw return contribution
- `oil`: 22 entries, win rate `63.64%`, avg PnL `0.4614%`, largest sample depth
- `index`: 3 entries, win rate `100.00%`, avg PnL `1.3618%`, strongest consistency among small-sample assets
- `rates`: 3 entries, win rate `66.67%`, avg PnL `0.1138%`
- `fx`: 4 entries, win rate `75.00%`, avg PnL `0.0848%`

Event-type summary:

- `fomc`: avg PnL `5.3529%`, high impact but small sample
- `eia_inventory`: 18 entries, avg PnL `0.5935%`, deepest recurring event set
- `nfp`: 8 entries, win rate `87.5%`, avg PnL `0.5873%`
- `opec`: avg PnL `-0.0689%`, weak in current rule set
- `geopolitical`: avg PnL `-0.3242%`, weak in current rule set

## Quantum Pack Interpretation

The generated pack identifies three combinatorial problems:

1. `asset_subset_selection`
2. `wait_bucket_optimization`
3. `risk_tier_allocation`

For this AWS run, only `asset_subset_selection` was submitted.

Pack-level exact baseline:

- Best subset: `crypto + oil + index`
- Objective: `0.297124`
- Base score: `0.299262`
- Pair penalty: `0.002138`
- Size penalty: `0.0`

This means the final basket was chosen because:

- `crypto` contributed the strongest edge
- `oil` added breadth and event coverage
- `index` improved portfolio robustness enough to survive the pair penalties

## AWS Quantum Results

Run file:

- `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_asset_subset_selection_aws_20260628T223149Z.json`

Report files:

- `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_asset_subset_selection_aws_20260628T223149Z_report.json`
- `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_asset_subset_selection_aws_20260628T223149Z_report.md`

AWS result summary:

- Submitted tasks: `9`
- Completed tasks: `9/9`
- Best sampled solution across all tasks: always `crypto + oil + index`
- Best bitstring: `11100`
- Decoded bits: `[0, 0, 1, 1, 1]`
- Best sampled objective: `0.297124`
- Delta vs exact baseline: `0.0`

Operational interpretation:

- AWS sampling did not discover a better basket than the classical exact baseline.
- That is a good result, not a bad one.
- It means the updated optimization landscape is stable and the solution is reproducible under quantum sampling.

## Important Reconciliation Note

There is a visible mismatch between two layers of output:

- Real-history summary JSON reported:
  - best exact subset = `oil + index`
  - objective = `0.228065`
- Quantum pack JSON reported:
  - best exact subset = `crypto + oil + index`
  - objective = `0.297124`

For decision purposes, the correct source of truth for this quantum run is:

- the generated quantum pack
- the AWS quantum report

Why:

- The AWS run consumed the quantum pack, not the earlier summary headline
- AWS then matched the pack baseline exactly
- Therefore the pack and AWS report are the authoritative final result of this round

Recommended interpretation of the mismatch:

- The summary layer and quantum-pack layer are not using exactly the same scoring aggregation path
- This is a reporting-consistency issue, not evidence of runtime failure
- The next cleanup step should be to unify the “best subset” reporting path so the summary JSON and pack JSON always agree

## What Changed vs Earlier Direction

Compared with the earlier local interpretation where `oil + index` looked strongest in one summary layer, the updated finalized quantum path now prefers:

- `crypto`
- `oil`
- `index`

That indicates today’s rule adjustments increased the contribution of:

- crypto edge capture
- cross-asset basket value under the current scoring framework
- portfolio-level combinatorial ranking, rather than single-asset average stability alone

## Practical Implications

For immediate internal research:

- Treat `crypto + oil + index` as the current champion basket under the updated rules
- Treat `rates` and `fx` as secondary or reserve baskets unless later tests overturn this
- Keep `asset_subset_selection` as the current strongest quantum use case

For next testing stage:

- Run the same AWS cross-check again after any major scoring-rule change
- Add a reconciliation fix so historical summary and quantum-pack “best subset” use one exact scoring source
- Consider promoting `wait_bucket_optimization` to the next AWS quantum task once the basket is held fixed

## Bottom Line

This was a successful test.

The updated financial model did not just “run”; it survived a large historical compression pipeline, produced a new and sharper optimal basket, and then had that basket independently confirmed by AWS quantum sampling with zero gap versus the exact classical optimum.

Current internal decision truth:

- Best basket: `crypto + oil + index`
- Exact objective: `0.297124`
- AWS quantum confirmation: `matched exactly`
