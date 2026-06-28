# EventAlpha Quantum Candidate Pack From Real History

- generated_at: 2026-06-28T22:51:52.870893+00:00
- cases_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_cases_20260628T225142Z.csv`
- matrix_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_matrix_20260628T225142Z.csv`

## Why Quantum Matters Here

- `asset_subset_selection`: This now comes from real historical case-by-asset payoff data, not a toy heuristic.
- `wait_bucket_optimization`: This uses observed wait distributions and confidence structure from the real-history validation run.
- `risk_tier_allocation`: This uses the historically strongest subset and allocates abstract risk tiers under a hard budget.

## Asset Stats

- `fx`: samples=4, evidence=LOW, weighted_avg_pnl_pct=-0.102, weighted_win_rate=66.2%, avg_wait_seconds=133.5, memory_edge=0.964
- `rates`: samples=3, evidence=LOW, weighted_avg_pnl_pct=0.199, weighted_win_rate=78.7%, avg_wait_seconds=87.7, memory_edge=0.947
- `crypto`: samples=3, evidence=LOW, weighted_avg_pnl_pct=7.665, weighted_win_rate=63.6%, avg_wait_seconds=354.0, memory_edge=0.886
- `oil`: samples=22, evidence=MEDIUM, weighted_avg_pnl_pct=0.255, weighted_win_rate=60.5%, avg_wait_seconds=390.5, memory_edge=0.793
- `index`: samples=3, evidence=LOW, weighted_avg_pnl_pct=1.674, weighted_win_rate=100.0%, avg_wait_seconds=124.7, memory_edge=0.912

## Exact Baseline

- best subset: ['crypto', 'index', 'oil', 'rates'] | objective=9.815812
- best risk allocation: {"crypto": {"tier": "heavy", "weight": 1.5}, "index": {"tier": "normal", "weight": 1.0}, "oil": {"tier": "skip", "weight": 0.0}, "rates": {"tier": "skip", "weight": 0.0}} | objective=13.369854225018022

This pack contains only abstract optimization inputs derived from real historical validation. It places no orders and touches no broker.
