# EventAlpha Quantum Tools

These scripts support abstract IBM Quantum experiments for the five financial models.
They do not place orders and do not touch broker execution.

## Main scripts

- `ibm_quantum_eventalpha_submit.py`
  - Runs one problem locally or submits it to IBM Quantum.
- `ibm_quantum_eventalpha_status.py`
  - Checks submitted IBM jobs and fetches decoded results.
- `run_eventalpha_quantum_suite.py`
  - One-shot wrapper that runs local subset / wait / risk reviews and can optionally submit one selected problem to IBM.

## Example commands

```bash
python3 quantum_tools/ibm_quantum_eventalpha_submit.py --mode local --problem asset_subset_selection
python3 quantum_tools/ibm_quantum_eventalpha_submit.py --mode local --problem wait_bucket_optimization --asset oil
python3 quantum_tools/run_eventalpha_quantum_suite.py --shots 128 --grid-points 2
```

## Current operating rule

- `asset_subset_selection`: keep local exact/classical result as decision truth for now.
- `wait_bucket_optimization`: use quantum as a research tool only.
- `risk_tier_allocation`: use quantum as a research tool only.
