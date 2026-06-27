# IBM Quantum Real-History Risk Tier Allocation Result

- generated_at: `2026-06-27T05:33:20Z`
- run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_risk_tier_allocation_ibm_20260627T053304Z.json`
- pack_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_real_history_20260627T052656Z.json`

## Local Exact Baseline

- allocation:
  - `crypto` -> `heavy` (`1.5`)
  - `oil` -> `skip` (`0.0`)
  - `index` -> `normal` (`1.0`)
- risk_used: `2.5`
- objective: `24.247017`

## IBM Quantum Result Summary

All 4 submitted jobs returned `DONE`, but unlike the asset-subset run, IBM did **not** cleanly recover the local exact optimum on this more constrained allocation problem.

This is still useful, because it shows where quantum sampling is currently strong and where constraint handling becomes the bottleneck.

## Per-Job Best Sampled Solution

1. `d8vm1386c68s73agvndg`
   - params: `γ=[0.0]`, `β=[0.0]`
   - best sampled allocation:
     - `crypto` -> `normal` (`1.0`)
     - `oil` -> `normal` (`1.0`)
     - `index` -> `small` (`0.5`)
   - risk_used: `2.5`
   - one_hot_valid: `true`
   - objective: `19.338288`

2. `d8vm13mmvj5c73ei3cig`
   - params: `γ=[0.0]`, `β=[1.5707963267948966]`
   - best sampled allocation:
     - `crypto` -> `skip` (`0.0`)
     - `oil` -> `small` (`0.5`)
     - `index` -> `normal` (`1.0`)
   - risk_used: `1.5`
   - one_hot_valid: `true`
   - objective: `9.054401`

3. `d8vm13umvj5c73ei3cjg`
   - params: `γ=[3.141592653589793]`, `β=[0.0]`
   - best sampled allocation:
     - `crypto` -> `skip` (`0.0`)
     - `oil` -> `heavy` (`1.5`)
     - `index` -> `small` (`0.5`)
   - risk_used: `2.0`
   - one_hot_valid: `true`
   - objective: `10.085097`

4. `d8vm140pknjs73a193rg`
   - params: `γ=[3.141592653589793]`, `β=[1.5707963267948966]`
   - best sampled allocation:
     - `crypto` -> `normal` (`1.0`)
     - `oil` -> `small` (`0.5`)
     - `index` -> `small` (`0.5`)
   - risk_used: `2.0`
   - one_hot_valid: `false`
   - objective: `40.617767`

## Important Interpretation

The highest reported sampled objective was `40.617767`, but that sample is **not valid** because:

- `one_hot_valid = false`

That means the bitstring violated the required tier-assignment constraint, so it cannot be used as a real allocation answer.

Among the **valid** sampled solutions, the best IBM result was:

- `crypto = normal`
- `oil = normal`
- `index = small`
- objective = `19.338288`

This is meaningfully below the local exact optimum of `24.247017`.

## What This Means

This is the right conclusion for now:

1. `asset_subset_selection` was mature enough for IBM Quantum to reproduce the classical exact winner.
2. `risk_tier_allocation` is harder because the constraint structure is tighter.
3. IBM Quantum is already producing valid candidate allocations, but it is **not yet beating or matching** the classical exact solver on this formulation.

## Practical Decision Rule

For production logic, keep the classical exact result as truth:

- `crypto heavy`
- `oil skip`
- `index normal`

Use the IBM outputs here as:

- research evidence
- alternative candidate allocations
- guidance for improving the Ising / penalty encoding

## Best Next Step

Before scaling this problem further, the best improvement path is:

1. strengthen the one-hot penalty encoding
2. add a post-filter that ranks only valid sampled bitstrings
3. rerun the same real-history pack

Only after that should we judge whether IBM Quantum can genuinely help on the tier-allocation layer.
