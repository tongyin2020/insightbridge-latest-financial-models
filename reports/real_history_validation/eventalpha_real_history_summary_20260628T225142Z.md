# EventAlpha Real-History Validation Report

- generated_at: `2026-06-28T22:51:42.191778+00:00`
- event_cases: **374**
- asset_decisions: **1870**
- entry_decisions: **35**
- selected_portfolio_entries: **35**

## Headline KPIs

- all entry win rate: **68.6%**
- all entry avg pnl: **1.05%**
- selected portfolio win rate: **68.6%**
- selected portfolio avg pnl: **1.05%**
- top-confidence avg pnl: **1.77%**
- top-confidence win rate: **61.5%**

## Best Exact Asset Subset

- subset: **crypto, index, oil, rates**
- objective: `9.816`
- weighted mean pnl per case: `9.79%`
- weighted win rate: `75.7%`

## Year Weights

- `2025`: 1.5
- `2024`: 1.3
- `2023`: 1.1
- `2022`: 1.0
- `2021`: 0.85
- `2020`: 0.75
- `2019`: 0.65
- `2018`: 0.55

## By Asset

- `crypto`: samples=3, evidence=LOW, weighted_win_rate=63.6%, weighted_avg_pnl=7.67%, avg_conf=0.886
- `index`: samples=3, evidence=LOW, weighted_win_rate=100.0%, weighted_avg_pnl=1.67%, avg_conf=0.912
- `oil`: samples=22, evidence=MEDIUM, weighted_win_rate=60.5%, weighted_avg_pnl=0.26%, avg_conf=0.793
- `rates`: samples=3, evidence=LOW, weighted_win_rate=78.7%, weighted_avg_pnl=0.20%, avg_conf=0.947
- `fx`: samples=4, evidence=LOW, weighted_win_rate=66.2%, weighted_avg_pnl=-0.10%, avg_conf=0.964

## By Event Type

- `fomc`: samples=4, evidence=LOW, weighted_win_rate=52.3%, weighted_avg_pnl=5.06%
- `nfp`: samples=8, evidence=LOW, weighted_win_rate=90.0%, weighted_avg_pnl=0.56%
- `eia_inventory`: samples=18, evidence=LOW, weighted_win_rate=73.5%, weighted_avg_pnl=0.41%
- `liquidity_shock`: samples=1, evidence=LOW, weighted_win_rate=100.0%, weighted_avg_pnl=0.34%
- `opec`: samples=3, evidence=LOW, weighted_win_rate=32.4%, weighted_avg_pnl=-0.11%
- `geopolitical`: samples=1, evidence=LOW, weighted_win_rate=0.0%, weighted_avg_pnl=-0.32%

## Quantum Value

- This validation now produces a real historical case-by-asset payoff matrix.
- The strongest immediate IBM Quantum candidate is **asset subset selection** over the five-asset basket, because it is discrete, cross-case, and already has an exact local baseline for comparison.
