# EventAlpha Quantum Candidate Pack

- generated_at: 2026-06-27T02:54:50.340093+00:00
- event_type: opec
- db_path: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/eventalpha_memory.sqlite`

## Best uses for IBM Quantum now

- `best_asset_subset`: This is a discrete combinatorial selection problem with pairwise interaction penalties. Current gap: We still use heuristic ranking plus manual top-N cutoffs.
- `wait_bucket_choice`: The best wait bucket is discrete and event/regime-specific, not a smooth single formula. Current gap: Current wait logic is good but still partly heuristic and sample-light.
- `risk_tier_allocation`: Risk tiers across multiple chosen assets form a constrained allocation problem under a strict budget. Current gap: Current sizing logic is strong per asset, but cross-asset tier allocation is still approximate.

## Asset stats

- `fx`: samples=0, avg_pnl_pct=0.0, avg_wait_seconds=120.0, memory_edge=0.5, wait_bias=0, risk_bias=0.0
- `rates`: samples=0, avg_pnl_pct=0.0, avg_wait_seconds=120.0, memory_edge=0.5, wait_bias=0, risk_bias=0.0
- `crypto`: samples=0, avg_pnl_pct=0.0, avg_wait_seconds=120.0, memory_edge=0.5, wait_bias=0, risk_bias=0.0
- `oil`: samples=4, avg_pnl_pct=95.0, avg_wait_seconds=274.25, memory_edge=0.95, wait_bias=10, risk_bias=0.04
- `index`: samples=4, avg_pnl_pct=25.0, avg_wait_seconds=222.75, memory_edge=0.625, wait_bias=30, risk_bias=0.0

## Exact baseline results

- asset subset best solution: ['oil', 'index'] | objective=2.114
- wait best `fx`: 120s
- wait best `rates`: 120s
- wait best `crypto`: 120s
- wait best `oil`: 300s
- wait best `index`: 240s
- risk tier best allocation: {"oil": {"tier": "heavy", "weight": 1.5}, "index": {"tier": "normal", "weight": 1.0}} | risk_used=2.5 | objective=3.171

## Note

This pack contains only abstract optimization inputs and local replay summaries. It places no orders and touches no broker.
