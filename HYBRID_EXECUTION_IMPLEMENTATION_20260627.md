# EventAlpha Hybrid Execution Implementation

This project now contains a working hybrid execution layer aligned with the latest quantum findings.

## What was implemented

New files:

- `eventalpha_hybrid/__init__.py`
- `eventalpha_hybrid/hybrid_pipeline.py`
- `run_eventalpha_hybrid.py`
- `run_eventalpha_hybrid.sh`

## Current execution principle

**Quantum for discovery and timing, Classical for sizing and safety.**

Implemented behavior:

1. load the latest EventAlpha market states from all five adapters
2. build a unified event through `EventAlphaBrain`
3. read the latest quantum pack and latest IBM run artifacts
4. use the latest validated subset selection output as the candidate asset pool
5. use the latest validated wait-bucket output as the wait recommendation layer
6. apply a classical confidence filter
7. allocate risk through classical position sizing
8. apply execution guardrails
9. write a paper-only hybrid report under `reports/hybrid_runs/`

## Important constraint

This implementation intentionally does **not** use quantum `risk_tier_allocation` for production decisions.

That layer remains downgraded to classical logic because current IBM / QUBO performance is still weaker than the exact local baseline.

## Output location

Hybrid run outputs:

- `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/hybrid_runs/`

## Example

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_eventalpha_hybrid.py --event-type cpi --title "Hybrid CPI test" --top-n 3
```
