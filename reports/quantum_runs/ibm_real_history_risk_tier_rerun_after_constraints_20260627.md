# IBM Quantum Real-History Risk Tier Rerun After Constraint Fix

- generated_at: `2026-06-27T05:39:00Z`
- run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_risk_tier_allocation_ibm_20260627T053818Z.json`
- pack_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_real_history_20260627T052848Z.json`
- tooling_change: local patch applied to `/Users/tongyin/Desktop/Anaconda_Local_Tools/ibm_quantum_eventalpha_submit.py`

## What Was Fixed

Two important fixes were applied before this rerun:

1. `risk_tier_allocation` penalties were strengthened materially.
2. best-run selection logic was fixed so invalid solutions are no longer re-promoted later just because they have a larger raw objective.

## Local Exact Baseline

- allocation:
  - `crypto` -> `heavy` (`1.5`)
  - `oil` -> `skip` (`0.0`)
  - `index` -> `normal` (`1.0`)
- risk_used: `2.5`
- objective: `24.247017`

## Rerun Result

The rerun was cleaner from a constraint perspective, but it did **not** improve toward the classical optimum.

### Per-job best sampled solution

1. `d8vm3hpropqc738cl46g`
   - valid
   - allocation:
     - `crypto = skip`
     - `oil = skip`
     - `index = skip`
   - objective: `-50.0`

2. `d8vm3i86c68s73agvr10`
   - invalid
   - over budget (`risk_used = 3.5`)
   - objective: `20.623334`

3. `d8vm3immvj5c73ei3g4g`
   - valid
   - allocation:
     - `crypto = small`
     - `oil = skip`
     - `index = heavy`
   - risk_used: `2.0`
   - objective: `14.501288`

4. `d8vm3ig6c68s73agvr3g`
   - invalid
   - one-hot violation
   - objective: `-4.053591`

## Best Valid Result In This Rerun

The best valid IBM solution in the rerun was:

- `crypto = small`
- `oil = skip`
- `index = heavy`
- `risk_used = 2.0`
- `objective = 14.501288`

This is lower than:

- the original best valid IBM result: `19.338288`
- the local exact optimum: `24.247017`

## Interpretation

This rerun tells us something useful:

The earlier weakness was **not only** a reporting/ranking bug.

After fixing ranking and making the penalties much stronger, the quantum sampler still did not recover the classical optimum. In fact, the best valid solution moved further away from it.

That strongly suggests the current limitation is now more about:

1. sampling quality on this constrained encoding
2. the current abstract QUBO design itself

and less about simple reporting mistakes.

## Practical Conclusion

This is now a much cleaner conclusion:

- `asset_subset_selection` is quantum-ready in this workflow
- `wait_bucket_optimization` is close and mostly stable
- `risk_tier_allocation` is still a research problem, not a deployable quantum decision layer

## Recommended Next Step

Do **not** keep increasing penalties blindly.

The next meaningful improvement would be:

1. redesign the risk-tier encoding itself
2. possibly reduce the tier search space
3. or keep this layer classical while continuing quantum only on subset/wait tasks
