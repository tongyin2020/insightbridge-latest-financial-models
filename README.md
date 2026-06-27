# InsightBridge Latest Financial Models

This repository is the latest sanitized snapshot of the user's local InsightBridge financial trading model workspace.

It contains five model groups plus shared orchestration modules. This GitHub version is intentionally cleaned before publication:

- no live API key bundle
- no local SQLite database files
- no local transient WAL/SHM files
- no hardcoded Telegram production token

## Repository Structure

### 1. Crypto

Path: `01_Crypto_BTC_ETH_SOL`

Focus:

- BTC / ETH / SOL model logic
- backend signal generation
- websocket market feeds
- Telegram alert integration via environment variables

### 2. Stock Index

Path: `02_StockIndex_IBKR_ES_NQ`

Focus:

- IBKR paper-trading connector
- ES / NQ style index routing logic
- live trader entrypoints
- signal engine integration

### 3. FX

Path: `03_FX_AUD_NZD_EUR_GBP`

Focus:

- AUD / NZD / EUR / GBP trading workflows
- backend + frontend application stack
- adapters for broker connectivity
- risk, event, and execution gate logic

### 4. Oil

Path: `04_WTI_Oil_Futures`

Focus:

- WTI oil trading workflows
- replay, fragility, regime, execution-gate, and risk-control modules
- backend + frontend stack
- additional nested `Oil-Trading-System` implementation tree

### 5. Bond / Treasury

Path: `05_Bond_Treasury`

Focus:

- Treasury / bond trading workflows
- risk analytics, yield curve, portfolio optimizer, and paper-trading modules
- backend + frontend stack
- additional nested `Bond-Trading-System` implementation tree

### 6. Shared Modules

Top-level shared Python modules:

- `shared_quant_core.py`
- `shared_risk_guard.py`
- `shared_event_state_machine.py`
- `shared_monitoring_dashboard.py`
- `shared_crypto_tool_crewai.py`
- `shared_fx_tool_crewai.py`
- `shared_bond_tool_crewai.py`
- `shared_stockindex_tool_crewai.py`

These provide cross-model logic, orchestration, shared risk frameworks, and common quantitative utilities.

## Important Notes

### Sanitized GitHub Copy

This repository is a sanitized export of the user's newer local desktop version. Sensitive values and local runtime artifacts were removed before pushing.

### Local vs GitHub

The source of truth for raw development history remains the user's local Mac workspace. This repository is intended to preserve the latest safe-to-share code snapshot.

### Credentials

If you want to run any model locally, supply your own credentials through environment variables or local `.env` files that are not committed to GitHub.

Examples of secrets that must remain local:

- broker credentials
- market data API keys
- Telegram bot tokens
- cloud model provider keys

## Suggested Next Steps

1. Add model-specific setup notes inside each of the five model folders.
2. Replace placeholder subfolder READMEs with real run instructions.
3. Add one environment template per model if local execution will continue from this repository.
4. Add a release tag once the structure is considered stable.

## EventAlpha 2.1 Integration

This repository now also contains a unified EventAlpha integration layer:

- shared core: `eventalpha_core/`
- per-model adapters:
  - `01_Crypto_BTC_ETH_SOL/eventalpha_adapter.py`
  - `03_FX_AUD_NZD_EUR_GBP/backend/eventalpha_adapter.py`
  - `04_WTI_Oil_Futures/backend/eventalpha_adapter.py`
  - `05_Bond_Treasury/backend/eventalpha_adapter.py`
  - `02_StockIndex_IBKR_ES_NQ/eventalpha_adapter.py`
- unified paper runner:
  - `run_eventalpha_paper.py`
- verification script:
  - `verify_eventalpha_full_stack.py`

### What this means

The five financial models no longer need to operate as five fully separate decision systems.

Instead:

1. each model exposes:
   - `get_market_state()`
   - `execute_decision(decision)`
   - `manage_position(position)`
2. `EventAlphaBrain` ranks assets, scores event severity, fuses Bayesian confidence, applies waiting policy, and then sends decisions into the model adapters
3. the current implementation is paper-trading / research mode only

### Quick run

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_eventalpha_paper.py --event-type cpi --title "Manual CPI test" --top-n 2
```

### Hybrid execution run

The repository now also supports the newer hybrid architecture:

- quantum keeps `asset_subset_selection`
- quantum keeps `wait_bucket_optimization`
- classical takes back sizing, risk budget, and execution guardrails

Run it locally:

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_eventalpha_hybrid.py --event-type cpi --title "Hybrid CPI test" --top-n 3
```

Or with the shell wrapper:

```bash
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_eventalpha_hybrid.sh --event-type opec --title "Hybrid OPEC test"
```

Outputs are written to:

```bash
/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/hybrid_runs/
```

### Telegram trade alerts

If you want the unified EventAlpha runner to notify you when one of the five models reaches an actual paper-trade entry decision, keep these environment variables set locally:

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```

Or place them once in a local private file that is ignored by Git:

```bash
/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/.env.telegram.local
```

Example:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Then run:

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_eventalpha_paper.py --event-type cpi --title "Manual CPI test" --top-n 2 --telegram-alerts
```

Disable alerts explicitly with:

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_eventalpha_paper.py --event-type cpi --title "Manual CPI test" --top-n 2 --no-telegram-alerts
```

### Continuous local runtime

Start the five-model EventAlpha scan in the background:

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/manage_eventalpha_runtime.py start --interval-minutes 30 --top-n 5 --telegram-alerts
```

Run one full cycle immediately in the foreground:

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/manage_eventalpha_runtime.py once --top-n 5 --telegram-alerts
```

Check whether the background runtime is really alive:

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_eventalpha_runtime.py
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/manage_eventalpha_runtime.py status
```

Stop it cleanly:

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/manage_eventalpha_runtime.py stop
```

Runtime state and logs are written locally under:

```bash
/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/runtime_logs/
```

### Full verification

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/verify_eventalpha_full_stack.py
```

## Quantum Research Layer

The repository now includes a local research layer for reviewing EventAlpha quantum runs, tuning subset penalties, and opening a lightweight dashboard.

### One-shot research suite

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/run_quantum_research_suite.py
```

This generates:

- dashboard dataset CSV
- dashboard HTML views
- penalty tuning CSV / JSON
- penalty sensitivity markdown report

All outputs are written under:

```bash
/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_research/
```

### Serve the local dashboard

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/quantum_research/dashboard_app.py
```

Then open:

```bash
http://127.0.0.1:8050
```
