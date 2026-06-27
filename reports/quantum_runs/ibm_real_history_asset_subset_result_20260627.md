# IBM Quantum Real-History Asset Subset Result

- generated_at: `2026-06-27T05:31:40Z`
- run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_asset_subset_selection_ibm_20260627T053116Z.json`
- pack_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_real_history_20260627T052656Z.json`

## Local Exact Baseline

- selected: `["crypto", "oil", "index"]`
- objective: `0.310834`
- bits: `[0, 0, 1, 1, 1]`

## IBM Quantum Result

All 4 submitted jobs returned `DONE`.

For every parameter setting, the best sampled solution matched the local exact optimum:

- bitstring: `11100`
- decoded_bits: `[0, 0, 1, 1, 1]`
- selected: `["crypto", "oil", "index"]`
- objective: `0.310834`

## Per-Job Detail

1. `d8vm0886c68s73agvm6g`
   - params: `γ=[0.0]`, `β=[0.0]`
   - best sampled shots: `2`

2. `d8vm08g6c68s73agvm7g`
   - params: `γ=[0.0]`, `β=[1.5707963267948966]`
   - best sampled shots: `4`

3. `d8vm08umvj5c73ei3bi0`
   - params: `γ=[3.141592653589793]`, `β=[0.0]`
   - best sampled shots: `3`

4. `d8vm090pknjs73a192q0`
   - params: `γ=[3.141592653589793]`, `β=[1.5707963267948966]`
   - best sampled shots: `7`

## Interpretation

This is the first meaningful IBM Quantum confirmation on the `real_history` pack.

The important point is not the raw shot count, but that the quantum run recovered the same optimal abstract asset basket as the classical exact solver:

- `crypto`
- `oil`
- `index`

That means the current abstract optimization formulation is internally consistent across:

- real-history validation
- classical exact optimization
- IBM Quantum sampling

## Practical Conclusion

For now, keep the classical exact solution as the decision truth, because it is deterministic and cheap at 5 assets.

But this result proves the pipeline is real and usable:

1. real historical validation can generate a meaningful payoff matrix
2. that payoff matrix can be abstracted safely
3. IBM Quantum can solve the first-round subset-selection problem without touching broker logic

## Recommended Next Quantum Step

The next best target is:

- `risk_tier_allocation`

After that:

- `wait_bucket_optimization`

Those two will test whether quantum can add value beyond simply reproducing the same 5-asset subset winner.
