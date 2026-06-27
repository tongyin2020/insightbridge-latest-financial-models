# EventAlpha Real-History Validation Report

- generated_at: `2026-06-27T05:52:43.026056+00:00`
- event_cases: **154**
- asset_decisions: **770**
- entry_decisions: **14**
- selected_portfolio_entries: **14**

## Headline KPIs

- all entry win rate: **50.0%**
- all entry avg pnl: **1.24%**
- selected portfolio win rate: **50.0%**
- selected portfolio avg pnl: **1.24%**
- top-confidence avg pnl: **0.71%**
- top-confidence win rate: **75.0%**

## Best Exact Asset Subset

- subset: **rates, index**
- objective: `0.185`
- mean pnl per case: `0.03%`
- win rate: `2.6%`

## By Asset

- `crypto`: entries=2, win_rate=50.0%, avg_pnl=9.63%, avg_conf=0.909
- `index`: entries=2, win_rate=100.0%, avg_pnl=1.86%, avg_conf=0.950
- `rates`: entries=2, win_rate=100.0%, avg_pnl=0.35%, avg_conf=0.960
- `oil`: entries=7, win_rate=28.6%, avg_pnl=-0.74%, avg_conf=0.825
- `fx`: entries=1, win_rate=0.0%, avg_pnl=-1.12%, avg_conf=0.989

## By Event Type

- `fomc`: entries=4, win_rate=50.0%, avg_pnl=5.35%
- `nfp`: entries=2, win_rate=100.0%, avg_pnl=0.40%
- `liquidity_shock`: entries=1, win_rate=100.0%, avg_pnl=0.34%
- `opec`: entries=3, win_rate=33.3%, avg_pnl=-0.07%
- `geopolitical`: entries=1, win_rate=0.0%, avg_pnl=-0.32%
- `eia_inventory`: entries=3, win_rate=33.3%, avg_pnl=-1.55%

## Quantum Value

- This validation now produces a real historical case-by-asset payoff matrix.
- The strongest immediate IBM Quantum candidate is **asset subset selection** over the five-asset basket, because it is discrete, cross-case, and already has an exact local baseline for comparison.
