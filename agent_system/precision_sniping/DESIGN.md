# Precision Sniping & Impulse Wave Integration — Design Plan

Source: `Precision_Sniping__Impulse_Wave_Integration_Blueprint.docx`

## Goal

Add a higher-precision entry/exit layer on top of the `agent_system` crisis subgraph. The layer enforces:
1. Cross-asset regime interlock (80% confidence before arming).
2. Microstructural false-breakout filter with dynamic cooling-off + OFI.
3. In-flight kinetic tracker (velocity/acceleration) for exit before momentum apex.
4. Unified coordinator with lockout and position-size scaling across correlated bots.

## Components to add

### 1. CrossAssetInterlock (`regime_interlock.py`)

- Input: the 5 bot snapshots from `agent_system.adapters.BotFactory`.
- Computes a composite `regime_score` from:
  - fraction of bots with aligned direction (`long`/`short`)
  - average expected-move magnitude across shadow logs
  - news wake count across asset classes
  - microstructure warning ratio (if high warnings, reduce score)
- Classifies regime type:
  - `FX_INTERVENTION` when fx bot is dominant and high-move in FX
  - `OIL_GEOPOL` when oil bot is dominant and commodity shock keywords present
  - `GENERIC` otherwise
- Outputs `InterlockResult` with `score`, `regime_type`, `primary_bot`, `secondary_bots`, `secondary_position_scale`.

### 2. MicrostructureBreakoutFilter (`breakout_filter.py`)

- State machine: `MONITORING` → `ARMED` → `IN_TRADE`.
- `arm(score)`: transition when `regime_score >= min_confidence`.
- `validate_breakout(current_price, l2_book)`:
  - waits `cooling_off_minutes`
  - computes OFI ratio of top-3 bid/ask sizes
  - enters `IN_TRADE` if `bid_sizes / ask_sizes >= ofi_imbalance_ratio`

### 3. KineticInFlightBacktester (`kinetic_tracker.py`)

- Records price series per open position.
- Fits 2nd-degree polynomial to last 7 points.
- Returns `HOLD`, `EXIT_MOMENTUM`, or `EXIT_TTL`:
  - `EXIT_TTL` when `elapsed_mins >= pulse_ttl_minutes`
  - `EXIT_MOMENTUM` when `current_return >= 0.4%`, `velocity < 0.02`, `acceleration < -0.01`

### 4. UnifiedExecutionCoordinator (`coordinator.py`)

- Ties the above into a single `process_signal(signal, price, l2_book)` loop.
- For entry: uses interlock + breakout filter.
- For open positions: uses kinetic tracker for exits.
- On exit: sets a 2-hour lockout.
- Returns `NO_ACTION`, `SYSTEM_ARMED`, `BUY_MARKET`, `SELL_MARKET`, `LOCKOUT_ACTIVE`, `TRACKING_PULSE`.

### 5. PositionRiskBalancer (`risk_balancer.py`)

- When a primary bot enters `IN_TRADE`, reduce allowed size of correlated secondary bots by 75%.

## Integration points

- `ExecutionBridge` gets a new method `apply_precision_layer(actions, snapshots)`.
- If `AGENT_PRECISION_SNIPING=1`, each consensus action is routed through `UnifiedExecutionCoordinator`.
- The coordinator needs live price and L2. Since the current `run_agent_system.py` is batch/log-driven, the first cut reads `timeseries_shadow.log` and `microstructure_shadow.log` as a proxy feed; a future cut wires into TWS/IBKR live market data.
- Add `PRECISION_SNIPING_ENABLED` to `AgentConfig` and `cfg/agents.yaml`.

## Safety

- Default off.
- Even when enabled, `AGENT_OBSERVE_ONLY=1` and `AGENT_EXECUTION_ENABLED=0` prevent broker orders.
- Any `EXIT_SIGNAL` is first logged as `would_exit` and only later executed with a kill-switch.

## Tests

- `test_precision_sniping.py` covering:
  - interlock score crossing 80%
  - breakout filter cooling-off + OFI
  - kinetic tracker exit on velocity decay
  - coordinator end-to-end lockout
