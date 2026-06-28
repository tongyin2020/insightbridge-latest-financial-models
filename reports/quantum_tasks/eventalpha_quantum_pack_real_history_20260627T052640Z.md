# EventAlpha Quantum Candidate Pack From Real History

- generated_at: 2026-06-27T05:26:40.588396+00:00
- cases_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_cases_20260627T052151Z.csv`
- matrix_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_matrix_20260627T052151Z.csv`

## Why Quantum Matters Here

- `asset_subset_selection`: This now comes from real historical case-by-asset payoff data, not a toy heuristic.
- `wait_bucket_optimization`: This uses observed wait distributions and confidence structure from the real-history validation run.
- `risk_tier_allocation`: This uses the historically strongest subset and allocates abstract risk tiers under a hard budget.

## Asset Stats

- `fx`: samples=1, avg_pnl_pct=-1.119, win_rate=0.0%, avg_wait_seconds=153.3, memory_edge=0.887
- `rates`: samples=2, avg_pnl_pct=0.349, win_rate=100.0%, avg_wait_seconds=121.5, memory_edge=0.968
- `crypto`: samples=2, avg_pnl_pct=9.628, win_rate=50.0%, avg_wait_seconds=212.5, memory_edge=0.837
- `oil`: samples=6, avg_pnl_pct=0.695, win_rate=50.0%, avg_wait_seconds=242.5, memory_edge=0.644
- `index`: samples=2, avg_pnl_pct=1.860, win_rate=100.0%, avg_wait_seconds=162.4, memory_edge=0.876

## Exact Baseline

- best subset: ['crypto', 'oil', 'index'] | objective=0.373808
- best risk allocation: {"crypto": {"tier": "heavy", "weight": 1.5}, "oil": {"tier": "skip", "weight": 0.0}, "index": {"tier": "normal", "weight": 1.0}} | objective=27.183238

This pack contains only abstract optimization inputs derived from real historical validation. It places no orders and touches no broker.
