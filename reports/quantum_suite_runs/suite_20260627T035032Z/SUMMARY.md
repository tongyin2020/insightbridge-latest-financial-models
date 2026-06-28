# EventAlpha Quantum Suite Summary

- generated_at: 2026-06-27T03:50:35.209049+00:00
- pack_path: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_opec_20260627T025713Z.json`

## Local Problems

### asset_subset_selection

- returncode: 0
- baseline_exact: `{"bits": [0, 0, 0, 1, 1], "selected": ["oil", "index"], "objective": 2.114, "base": 2.314, "pair_penalty": 0.2, "size_penalty": 0.0}`
- best_sampled_solution: `{"bitstring": "11000", "decoded_bits": [0, 0, 0, 1, 1], "shots": 6, "objective": 2.114, "selected": ["oil", "index"]}`

### wait_bucket_optimization

- returncode: 0
- baseline_exact: `{"asset": "oil", "wait_seconds": 300, "score": 1.2525}`
- best_sampled_solution: `{"bitstring": "001000", "decoded_bits": [0, 0, 0, 1, 0, 0], "shots": 4, "objective": 0.9575, "asset": "oil", "selected_waits": [180], "chosen_wait_seconds": 180, "one_hot_valid": true}`

### risk_tier_allocation

- returncode: 0
- baseline_exact: `{"allocation": {"oil": {"tier": "heavy", "weight": 1.5}, "index": {"tier": "normal", "weight": 1.0}}, "risk_used": 2.5, "objective": 3.171}`
- best_sampled_solution: `{"bitstring": "00011000", "decoded_bits": [0, 0, 0, 1, 1, 0, 0, 0], "shots": 1, "objective": 2.221, "allocation": {"oil": {"tier": "heavy", "weight": 1.5}, "index": {"tier": "skip", "weight": 0.0}}, "risk_used": 1.5, "one_hot_valid": true}`

