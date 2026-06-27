# EventAlpha Quantum Suite Summary

- generated_at: 2026-06-27T06:31:20.334036+00:00
- pack_path: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_real_history_20260627T063104Z.json`

## Local Problems

### asset_subset_selection

- returncode: 0
- baseline_exact: `{"bits": [0, 0, 1, 1, 1], "selected": ["crypto", "oil", "index"], "objective": 0.297124, "base": 0.299262, "pair_penalty": 0.002138, "size_penalty": 0.0}`
- best_sampled_solution: `{"bitstring": "11100", "decoded_bits": [0, 0, 1, 1, 1], "shots": 13, "objective": 0.297124, "selected": ["crypto", "oil", "index"]}`

### wait_bucket_optimization

- returncode: 0
- baseline_exact: `{"asset": "oil", "wait_seconds": 300, "score": 0.946806}`
- best_sampled_solution: `{"bitstring": "100000", "decoded_bits": [0, 0, 0, 0, 0, 1], "shots": 28, "objective": 0.946806, "asset": "oil", "selected_waits": [300], "chosen_wait_seconds": 300, "one_hot_valid": true, "constraint_valid": true}`

### risk_tier_allocation

- returncode: 0
- baseline_exact: `{"allocation": {"crypto": {"tier": "heavy", "weight": 1.5}, "oil": {"tier": "skip", "weight": 0.0}, "index": {"tier": "normal", "weight": 1.0}}, "risk_used": 2.5, "objective": 24.247061}`
- best_sampled_solution: `{"bitstring": "010000011000", "decoded_bits": [0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 1, 0], "shots": 1, "objective": 24.24706, "allocation": {"crypto": {"tier": "heavy", "weight": 1.5}, "oil": {"tier": "skip", "weight": 0.0}, "index": {"tier": "normal", "weight": 1.0}}, "risk_used": 2.5, "one_hot_valid": true, "budget_valid": true, "constraint_valid": true}`

## IBM Submission

- problem: `asset_subset_selection`
- returncode: 0
- stderr: `qiskit_runtime_service._discover_account:WARNING:2026-06-27 01:31:08,529: Loading account with the given token. A saved account will not be used.
qiskit_runtime_service.__init__:WARNING:2026-06-27 01:31:11,204: Instance was not set at service instantiation. Free and trial plan instances will be prioritized. Based on the following filters: (tags: None, region: us-east, eu-de), and available plans: (open), the available account instances are: open-instance. If you need a specific instance set it explicitly either by using a saved account with a saved default instance or passing it in directly to QiskitRuntimeService().
qiskit_runtime_service.backends:WARNING:2026-06-27 01:31:11,204: Using instance: open-instance, plan: open`

