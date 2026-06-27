# EventAlpha Penalty Sensitivity Report

- source_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_research/penalty_results.csv`
- total_grid_rows: 144
- unique_winner_count: 2
- robust_preferred_subset: `fx_fomc_001|oil_opec_001|index_nfp_001`
- robust_preferred_share: 77.1%

## Winner Frequency

- `fx_fomc_001|oil_opec_001|index_nfp_001` -> 111 / 144 (77.1%)
- `fx_fomc_001|crypto_geo_001|oil_opec_001|index_nfp_001` -> 33 / 144 (22.9%)

## Correlation Penalty Regimes

- `lambda_corr=0.5` -> `fx_fomc_001|oil_opec_001|index_nfp_001` wins 36 times
- `lambda_corr=1.0` -> `fx_fomc_001|oil_opec_001|index_nfp_001` wins 36 times
- `lambda_corr=1.5` -> `fx_fomc_001|oil_opec_001|index_nfp_001` wins 39 times

## Size Penalty Regimes

- `lambda_size=0.0` -> `fx_fomc_001|oil_opec_001|index_nfp_001` wins 27 times
- `lambda_size=0.05` -> `fx_fomc_001|oil_opec_001|index_nfp_001` wins 27 times
- `lambda_size=0.1` -> `fx_fomc_001|oil_opec_001|index_nfp_001` wins 27 times
- `lambda_size=0.15` -> `fx_fomc_001|oil_opec_001|index_nfp_001` wins 30 times

## Interpretation

The stable winner is the subset that dominates across the widest penalty surface, not just at one tuned point.
If one subset wins more than 60% of the grid, it can be treated as a robust preferred allocation for the current EventAlpha case pack.
