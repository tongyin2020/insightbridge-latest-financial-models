# EventAlpha AWS Quantum Cross-Check

- generated_at: 2026-06-28T22:32:24.755279+00:00
- run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_asset_subset_selection_aws_20260628T223149Z.json`
- problem: `asset_subset_selection`

## Exact Baseline

{
  "bits": [
    0,
    0,
    1,
    1,
    1
  ],
  "selected": [
    "crypto",
    "oil",
    "index"
  ],
  "objective": 0.297124,
  "base": 0.299262,
  "pair_penalty": 0.002138,
  "size_penalty": 0.0
}

## Best AWS Quantum Solution

{
  "bitstring": "11100",
  "decoded_bits": [
    0,
    0,
    1,
    1,
    1
  ],
  "shots": 13,
  "objective": 0.297124,
  "selected": [
    "crypto",
    "oil",
    "index"
  ]
}

## Delta vs Exact

0.0

## Recommendation

AWS quantum sample matched or exceeded the local exact baseline.