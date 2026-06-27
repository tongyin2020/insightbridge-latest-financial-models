# IBM Quantum Rerun on Latest Real-History Pack

- generated_at: 2026-06-27
- pack: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks/eventalpha_quantum_pack_real_history_20260627T055326Z.json`

## 1. Asset Subset Selection

- run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_asset_subset_selection_ibm_20260627T055612Z.json`
- classical exact baseline: `['crypto', 'oil', 'index']`
- baseline objective: `0.310834`

### IBM result

IBM again recovered the exact same best subset:

- `['crypto', 'oil', 'index']`
- objective: `0.310834`

This means the latest rerun continues to confirm:

- `asset_subset_selection` is stable
- IBM quantum sampling can match the classical exact optimum on this layer

## 2. Wait Bucket Optimization

- run_file: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs/eventalpha_quantum_run_wait_bucket_optimization_ibm_20260627T055840Z.json`

### Classical exact wait baseline

- `crypto`: `180s`
- `fx`: `120s`
- `index`: `120s`
- `oil`: `240s`
- `rates`: `120s`

### IBM result

The best visible task in this rerun was:

- asset: `fx`
- chosen wait: `120s`
- objective: `1.166316`

This exactly matches the classical baseline for `fx`.

The rerun therefore supports the same practical conclusion as before:

- `wait_bucket_optimization` is a valid quantum candidate
- at minimum, the current IBM run is not diverging away from the known classical optimum

## 3. Practical Interpretation

This latest rerun strengthens the current production architecture:

1. keep `asset_subset_selection` in the quantum layer
2. keep `wait_bucket_optimization` in the quantum layer
3. keep `risk_tier_allocation` in the classical layer

In short:

**Quantum for subset + wait, Classical for sizing + safety** remains the correct production blueprint.
