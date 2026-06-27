# EventAlpha Real-History Validation Report

- generated_at: `2026-06-27T05:21:51.789963+00:00`
- event_cases: **134**
- asset_decisions: **670**
- entry_decisions: **13**
- selected_portfolio_entries: **13**

## Headline KPIs

- all entry win rate: **61.5%**
- all entry avg pnl: **2.06%**
- selected portfolio win rate: **61.5%**
- selected portfolio avg pnl: **2.06%**
- top-confidence avg pnl: **0.71%**
- top-confidence win rate: **75.0%**

## Best Exact Asset Subset

- subset: **rates, oil, index**
- objective: `0.320`
- mean pnl per case: `0.06%`
- win rate: `5.2%`

## By Asset

- `crypto`: entries=2, win_rate=50.0%, avg_pnl=9.63%, avg_conf=0.909
- `index`: entries=2, win_rate=100.0%, avg_pnl=1.86%, avg_conf=0.950
- `oil`: entries=6, win_rate=50.0%, avg_pnl=0.70%, avg_conf=0.846
- `rates`: entries=2, win_rate=100.0%, avg_pnl=0.35%, avg_conf=0.960
- `fx`: entries=1, win_rate=0.0%, avg_pnl=-1.12%, avg_conf=0.989

## By Event Type

- `fomc`: entries=4, win_rate=50.0%, avg_pnl=5.35%
- `eia_inventory`: entries=2, win_rate=100.0%, avg_pnl=2.35%
- `nfp`: entries=2, win_rate=100.0%, avg_pnl=0.40%
- `liquidity_shock`: entries=1, win_rate=100.0%, avg_pnl=0.34%
- `opec`: entries=3, win_rate=33.3%, avg_pnl=-0.07%
- `geopolitical`: entries=1, win_rate=0.0%, avg_pnl=-0.32%

## Quantum Value

- This validation now produces a real historical case-by-asset payoff matrix.
- The strongest immediate IBM Quantum candidate is **asset subset selection** over the five-asset basket, because it is discrete, cross-case, and already has an exact local baseline for comparison.
