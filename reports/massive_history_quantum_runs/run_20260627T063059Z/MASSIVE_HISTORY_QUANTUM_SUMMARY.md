# EventAlpha Massive History + IBM Quantum Run

- generated_at: 2026-06-27T06:31:26.081215+00:00
- real_history_cases_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_cases_20260627T063103Z.csv`
- real_history_matrix_csv: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_matrix_20260627T063103Z.csv`
- real_history_summary_json: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/real_history_validation/eventalpha_real_history_summary_20260627T063103Z.json`
- quantum_pack_json: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_real_history_20260627T063104Z.json`
- quantum_suite_dir: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_suite_runs/suite_20260627T063104Z`
- ibm_run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_asset_subset_selection_ibm_20260627T063120Z.json`

## Parameters

- start_year: `2018`
- end_year: `2025`
- top_n: `3`
- max_eia_cases: `240`
- top_k: `3`
- risk_budget: `2.5`
- shots: `512`
- grid_points: `3`
- wait_asset: `oil`
- backend: `ibm_fez`
- poll_interval: `20`
- max_polls: `12`
- ibm_problem: `asset_subset_selection`

## Step Return Codes

- real_history_validation: `0`
- build_quantum_pack: `0`
- quantum_suite: `0`
- ibm_status_fetch: `0`

## IBM Result

- jobs_done: `0` / `9`
- all_done: `False`
- best_quantum_solution: `null`

## Note

This orchestration uses real historical validation and abstract quantum optimization only. It places no trades and touches no broker.
