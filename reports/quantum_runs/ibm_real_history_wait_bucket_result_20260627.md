# IBM Quantum Real-History Wait Bucket Result

- generated_at: `2026-06-27T05:36:10Z`
- run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_wait_bucket_optimization_ibm_20260627T053504Z.json`
- pack_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_real_history_20260627T052848Z.json`

## Local Exact Baseline

- `crypto` -> `180s`
- `fx` -> `120s`
- `index` -> `120s`
- `oil` -> `240s`
- `rates` -> `120s`

## IBM Quantum Summary

This round was materially stronger than the `risk_tier_allocation` round.

Across the 5 assets and 20 submitted jobs, IBM Quantum mostly reproduced the same wait bucket choices as the local exact baseline.

## Asset-by-Asset Result

### crypto

Local baseline: `180s`

IBM results:
- 3 jobs returned `180s`
- 1 job returned `120s`

Conclusion:
- IBM mostly matched the local exact optimum for crypto.

### fx

Local baseline: `120s`

IBM results:
- 3 jobs returned `120s`
- 1 job returned `180s`

Conclusion:
- IBM mostly matched the local exact optimum for FX.

### index

Local baseline: `120s`

IBM results:
- 3 jobs returned `120s`
- 1 job returned `180s`

Conclusion:
- IBM mostly matched the local exact optimum for index.

### oil

Local baseline: `240s`

IBM results:
- 4 jobs returned `240s`

Conclusion:
- IBM perfectly matched the local exact optimum for oil.

### rates

Local baseline: `120s`

IBM results:
- 4 jobs returned `120s`

Conclusion:
- IBM perfectly matched the local exact optimum for rates.

## Overall Interpretation

This is the current ranking of the three real-history quantum tasks:

1. `asset_subset_selection`
   - strongest alignment with classical exact
   - fully matched

2. `wait_bucket_optimization`
   - very good alignment
   - mostly matched, and fully matched for oil and rates

3. `risk_tier_allocation`
   - weakest alignment so far
   - still useful for research, but not yet reliable as a decision engine

## Practical Conclusion

For current production truth:

- keep classical exact outputs as final decision authority

For quantum research value:

- `asset_subset_selection` is already validated
- `wait_bucket_optimization` is close to production-grade as a research module
- `risk_tier_allocation` still needs stronger constraint encoding and valid-sample filtering

## Recommendation

If we continue this line of work, the most valuable next improvement is not a new quantum problem first.

It is:

1. strengthen the `risk_tier_allocation` penalty design
2. add explicit valid-bitstring post-filtering
3. rerun the same real-history pack

That will tell us whether the weak point is the quantum hardware sampling, or simply our current abstract encoding.
