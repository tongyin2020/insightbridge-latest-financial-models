# EventAlpha Quantum Candidate Pack From Real History

- generated_at: 2026-06-27T05:26:56.994188+00:00
- cases_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_cases_20260627T052656Z.csv`
- matrix_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_matrix_20260627T052656Z.csv`

## Why Quantum Matters Here

- `asset_subset_selection`: This now comes from real historical case-by-asset payoff data, not a toy heuristic.
- `wait_bucket_optimization`: This uses observed wait distributions and confidence structure from the real-history validation run.
- `risk_tier_allocation`: This uses the historically strongest subset and allocates abstract risk tiers under a hard budget.

## Asset Stats

- `fx`: samples=4, avg_pnl_pct=0.085, win_rate=75.0%, avg_wait_seconds=126.1, memory_edge=0.873
- `rates`: samples=3, avg_pnl_pct=0.114, win_rate=66.7%, avg_wait_seconds=95.7, memory_edge=0.967
- `crypto`: samples=3, avg_pnl_pct=7.229, win_rate=66.7%, avg_wait_seconds=176.3, memory_edge=0.792
- `oil`: samples=22, avg_pnl_pct=1.086, win_rate=54.5%, avg_wait_seconds=224.8, memory_edge=0.563
- `index`: samples=3, avg_pnl_pct=1.362, win_rate=100.0%, avg_wait_seconds=141.0, memory_edge=0.854

## Exact Baseline

- best subset: ['crypto', 'oil', 'index'] | objective=0.310834
- best risk allocation: {"crypto": {"tier": "heavy", "weight": 1.5}, "oil": {"tier": "skip", "weight": 0.0}, "index": {"tier": "normal", "weight": 1.0}} | objective=24.247017

This pack contains only abstract optimization inputs derived from real historical validation. It places no orders and touches no broker.
