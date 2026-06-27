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
