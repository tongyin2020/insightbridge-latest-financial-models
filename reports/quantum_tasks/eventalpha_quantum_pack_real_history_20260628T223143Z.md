# EventAlpha Quantum Candidate Pack From Real History

- generated_at: 2026-06-28T22:31:43.052017+00:00
- cases_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_cases_20260628T223142Z.csv`
- matrix_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_matrix_20260628T223142Z.csv`

## Why Quantum Matters Here

- `asset_subset_selection`: This now comes from real historical case-by-asset payoff data, not a toy heuristic.
- `wait_bucket_optimization`: This uses observed wait distributions and confidence structure from the real-history validation run.
- `risk_tier_allocation`: This uses the historically strongest subset and allocates abstract risk tiers under a hard budget.

## Asset Stats

- `fx`: samples=4, avg_pnl_pct=0.085, win_rate=75.0%, avg_wait_seconds=128.4, memory_edge=0.873
- `rates`: samples=3, avg_pnl_pct=0.114, win_rate=66.7%, avg_wait_seconds=96.1, memory_edge=0.966
- `crypto`: samples=3, avg_pnl_pct=7.229, win_rate=66.7%, avg_wait_seconds=181.1, memory_edge=0.792
- `oil`: samples=22, avg_pnl_pct=0.461, win_rate=63.6%, avg_wait_seconds=311.8, memory_edge=0.562
- `index`: samples=3, avg_pnl_pct=1.362, win_rate=100.0%, avg_wait_seconds=142.8, memory_edge=0.849

## Exact Baseline

- best subset: ['crypto', 'oil', 'index'] | objective=0.297124
- best risk allocation: {"crypto": {"tier": "heavy", "weight": 1.5}, "oil": {"tier": "skip", "weight": 0.0}, "index": {"tier": "normal", "weight": 1.0}} | objective=24.241381

This pack contains only abstract optimization inputs derived from real historical validation. It places no orders and touches no broker.
