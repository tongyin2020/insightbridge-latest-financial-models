# EventAlpha Validation Upgrade Report

- generated_at: 2026-06-28T22:50:56.259973+00:00
- source: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_cases_20260628T223142Z.csv`

## Executive Recommendation

- Current champion basket: **crypto, index, oil, rates**
- Apply year weighting immediately.
- Use Evidence Score to prevent small-sample overconfidence.
- Promote AWS Quantum next task from asset subset selection to wait bucket optimization.
- Keep IBKR in paper/shadow or micro-contract mode until execution logs accumulate.

## Year Weights

- 2025: 1.5
- 2024: 1.3
- 2023: 1.1
- 2022: 1.0
- 2021: 0.85
- 2020: 0.75
- 2019: 0.65
- 2018: 0.55

## Top Asset Subsets

- ['crypto', 'index', 'oil', 'rates'] | objective=9.815812
- ['crypto', 'index', 'oil', 'rates', 'fx'] | objective=9.666053
- ['crypto', 'index', 'oil'] | objective=9.662656
- ['crypto', 'index', 'rates'] | objective=9.593527
- ['crypto', 'index', 'oil', 'fx'] | objective=9.512669
- ['crypto', 'index', 'rates', 'fx'] | objective=9.442022
- ['crypto', 'index'] | objective=9.402411
- ['crypto', 'index', 'fx'] | objective=9.289340
- ['crypto', 'oil', 'rates'] | objective=8.190231
- ['crypto', 'oil', 'rates', 'fx'] | objective=8.042020

## Sensitivity Analysis

- risk_budget=1.5 | best=['crypto', 'index', 'oil', 'rates'] | objective=9.795812
- risk_budget=2.0 | best=['crypto', 'index', 'oil', 'rates'] | objective=9.805812
- risk_budget=2.5 | best=['crypto', 'index', 'oil', 'rates'] | objective=9.815812
- risk_budget=3.0 | best=['crypto', 'index', 'oil', 'rates'] | objective=9.825812
- risk_budget=4.0 | best=['crypto', 'index', 'oil', 'rates'] | objective=9.845812

## Asset Evidence

- crypto: samples=3 | evidence=LOW | weighted_avg_pnl=7.6651% | weighted_win_rate=63.64%
- index: samples=3 | evidence=LOW | weighted_avg_pnl=1.6745% | weighted_win_rate=100.00%
- oil: samples=22 | evidence=MEDIUM | weighted_avg_pnl=0.2554% | weighted_win_rate=60.47%
- rates: samples=3 | evidence=LOW | weighted_avg_pnl=0.1992% | weighted_win_rate=78.69%
- fx: samples=4 | evidence=LOW | weighted_avg_pnl=-0.1018% | weighted_win_rate=66.15%

## Wait Bucket Optimization

- 5_10m: samples=22 | evidence=MEDIUM | weighted_avg_pnl=1.3366% | weighted_win_rate=59.94%
- 0_3m: samples=10 | evidence=LOW | weighted_avg_pnl=0.9292% | weighted_win_rate=92.70%
- 3_5m: samples=3 | evidence=LOW | weighted_avg_pnl=-0.6843% | weighted_win_rate=25.00%

## Risk Tier Allocation Top 3

- objective=13.369854 | total_weight=2.5 | allocation={'crypto': {'tier': 'heavy', 'weight': 1.5}, 'index': {'tier': 'normal', 'weight': 1.0}, 'oil': {'tier': 'skip', 'weight': 0.0}, 'rates': {'tier': 'skip', 'weight': 0.0}}
- objective=12.643380 | total_weight=2.5 | allocation={'crypto': {'tier': 'heavy', 'weight': 1.5}, 'index': {'tier': 'small', 'weight': 0.5}, 'oil': {'tier': 'small', 'weight': 0.5}, 'rates': {'tier': 'skip', 'weight': 0.0}}
- objective=12.621538 | total_weight=2.5 | allocation={'crypto': {'tier': 'heavy', 'weight': 1.5}, 'index': {'tier': 'small', 'weight': 0.5}, 'oil': {'tier': 'skip', 'weight': 0.0}, 'rates': {'tier': 'small', 'weight': 0.5}}