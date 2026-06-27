# EventAlpha Real-History Validation Report

- generated_at: `2026-06-27T05:53:25.786735+00:00`
- event_cases: **374**
- asset_decisions: **1870**
- entry_decisions: **35**
- selected_portfolio_entries: **35**

## Headline KPIs

- all entry win rate: **62.9%**
- all entry avg pnl: **1.44%**
- selected portfolio win rate: **62.9%**
- selected portfolio avg pnl: **1.44%**
- top-confidence avg pnl: **0.48%**
- top-confidence win rate: **77.8%**

## Best Exact Asset Subset

- subset: **oil, index**
- objective: `0.229`
- mean pnl per case: `0.07%`
- win rate: `4.0%`

## By Asset

- `crypto`: entries=3, win_rate=66.7%, avg_pnl=7.23%, avg_conf=0.886
- `index`: entries=3, win_rate=100.0%, avg_pnl=1.36%, avg_conf=0.940
- `oil`: entries=22, win_rate=54.5%, avg_pnl=1.09%, avg_conf=0.799
- `rates`: entries=3, win_rate=66.7%, avg_pnl=0.11%, avg_conf=0.947
- `fx`: entries=4, win_rate=75.0%, avg_pnl=0.08%, avg_conf=0.964

## By Event Type

- `fomc`: entries=4, win_rate=50.0%, avg_pnl=5.35%
- `eia_inventory`: entries=18, win_rate=61.1%, avg_pnl=1.36%
- `nfp`: entries=8, win_rate=87.5%, avg_pnl=0.59%
- `liquidity_shock`: entries=1, win_rate=100.0%, avg_pnl=0.34%
- `opec`: entries=3, win_rate=33.3%, avg_pnl=-0.07%
- `geopolitical`: entries=1, win_rate=0.0%, avg_pnl=-0.32%

## Quantum Value

- This validation now produces a real historical case-by-asset payoff matrix.
- The strongest immediate IBM Quantum candidate is **asset subset selection** over the five-asset basket, because it is discrete, cross-case, and already has an exact local baseline for comparison.
