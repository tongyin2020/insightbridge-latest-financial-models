# Dukascopy JForex Bridge Strategy

This adapter bridges the Python FastAPI trading backend with Dukascopy's JForex trading platform. The JForex strategy runs inside the Dukascopy JForex client, forwards market data to the Python backend, receives trading signals, and executes orders on Dukascopy.

## Architecture

```
Dukascopy JForex Platform
    |
    +-- DukascopyBridgeStrategy.java  (IStrategy implementation)
    |       |
    |       +-- HttpClient.java       (HTTP communication layer)
    |
    |   HTTP GET/POST
    v
Python FastAPI Backend (http://localhost:8001)
    |
    +-- /api/health              <-- health check
    +-- /api/signals/current     <-- signal polling
    +-- /api/settings            <-- trading settings
    +-- /api/broker/tick         <-- tick data forwarding
    +-- /api/broker/bar          <-- bar data forwarding
    +-- /api/broker/position     <-- position reporting
    +-- /api/broker/status       <-- adapter registration
```

## Prerequisites

1. **Dukascopy Demo or Live Account** -- register at https://www.dukascopy.com
2. **JForex Platform** -- download from Dukascopy after registration
3. **Java JDK 8 or higher** -- required for compilation
4. **Python Backend Running** -- the FastAPI backend must be running on `http://localhost:8001`

## Setup

### Step 1: Locate the JForex SDK JAR

After installing JForex, find the SDK JAR file. Typical locations:

- **macOS**: `~/Library/Application Support/JForex/libs/JForex-API-2.xx.x.jar`
- **Windows**: `C:\Users\<you>\AppData\Local\JForex\libs\JForex-API-2.xx.x.jar`
- **Linux**: `~/.jforex/libs/JForex-API-2.xx.x.jar`

If you cannot find it, look inside the JForex installation directory for any JAR file named `JForex-API-*.jar` or `DDS2-jClient-*.jar`.

You can also download the SDK separately from the Dukascopy wiki:
https://www.dukascopy.com/wiki/en/development/get-started-api

### Step 2: Compile the Strategy

Open a terminal and navigate to the adapter directory:

```bash
cd "/path/to/fx_trading_system/adapters/dukascopy"
```

Compile both Java files against the JForex SDK:

```bash
# Set the path to your JForex SDK JAR
JFOREX_JAR="$HOME/Library/Application Support/JForex/libs/JForex-API-2.13.63.jar"

# Compile
javac -cp "$JFOREX_JAR" -d out HttpClient.java DukascopyBridgeStrategy.java
```

If compilation succeeds, you will find class files under `out/adapters/dukascopy/`.

To package into a JAR (optional but recommended):

```bash
cd out
jar cf ../FXBridgeStrategy.jar adapters/dukascopy/*.class
cd ..
```

### Step 3: Load into JForex Platform

**Option A -- Load .jfx or .java file directly:**

1. Open JForex platform and log in.
2. Go to **Strategies** tab (or press Ctrl+S / Cmd+S).
3. Click **Open** and select `DukascopyBridgeStrategy.java`.
4. JForex will compile it in-place using its built-in compiler.
5. Click **Start** to run the strategy.

**Option B -- Load compiled JAR:**

1. Copy `FXBridgeStrategy.jar` into the JForex strategies folder:
   - macOS: `~/Library/Application Support/JForex/Strategies/`
   - Windows: `C:\Users\<you>\AppData\Local\JForex\Strategies\`
2. Restart JForex.
3. The strategy will appear in the **Strategies** list.
4. Click **Start** to run.

### Step 4: Configure the Backend URL

When you start the strategy, JForex will show a configuration dialog with these parameters:

| Parameter | Default | Description |
|---|---|---|
| Backend URL | `http://localhost:8000` | The URL of your Python FastAPI backend |
| Trade amount (lots) | `0.01` | Position size in lots (0.01 = 1 micro lot) |
| Tick forwarding interval (ms) | `1000` | How often ticks are sent to the backend |
| Signal poll interval (ms) | `2000` | How often signals are fetched from the backend |
| Max consecutive backend failures | `5` | Failures before safety shutdown triggers |

Set **Backend URL** to wherever your Python backend is running. For local development in this project it is typically `http://localhost:8001`. For a remote server, use the appropriate host and port.

## How It Works

### Signal Flow

1. On every tick (throttled to once per second), the strategy sends tick data to `POST /api/broker/tick`.
2. Every 2 seconds, it polls `GET /api/signals/current` for trading signals.
3. If a signal says **BUY** or **SELL** with confidence >= 50:
   - Checks that no existing position exists for that pair (max 1 per pair).
   - Checks that the current spread is below the threshold from backend settings.
   - Submits a market order with stop loss and take profit (bracket order).
4. If a signal says **FLATTEN**, all positions for that pair are closed.

### Bar Data

On every completed 5-minute bar, OHLCV data (mid-price from bid+ask) is sent to `POST /api/broker/bar`.

### Safety Mechanisms

- **Backend unreachable**: After 5 consecutive failed health checks, all positions are closed and trading is disabled. Trading resumes automatically when the backend comes back online.
- **Kill switch**: If the backend setting `kill_switch` is `true`, all positions are closed and no new trades are placed.
- **Override modes**: The strategy respects `NORMAL`, `OBSERVE_ONLY`, `REDUCE_ONLY`, and `FLATTEN_ALL` modes from the backend.
- **Time-based stop**: Positions held longer than `max_hold_minutes` (from backend settings) are automatically closed.
- **Spread filter**: Orders are rejected if the current spread exceeds `spread_threshold_pips`.
- **Single position per pair**: Only one open position is allowed per currency pair.

### Position Reporting

The strategy periodically reports all open position states to `POST /api/broker/position`, including:
- Direction, amount, entry price
- Current P&L in pips and USD
- Stop loss and take profit levels
- Order label and status

Lifecycle events (fill, close, reject) are also reported immediately.

## Troubleshooting

**Strategy does not start:**
- Ensure the JForex SDK JAR version matches your JForex platform version.
- Check the JForex console output for compilation errors.
- Make sure `HttpClient.java` is in the same directory as `DukascopyBridgeStrategy.java`.

**Backend connection fails:**
- Verify the Python backend is running: `curl http://localhost:8001/api/health`
- Check that no firewall is blocking localhost connections.
- If running on a different machine, update the Backend URL in strategy parameters.

**Orders are not being placed:**
- Check that `kill_switch` is not active: `curl http://localhost:8001/api/settings`
- Check that `override_mode` is set to `NORMAL`.
- Verify that signal confidence is >= 50 in the backend signals.
- Check the JForex console for spread-too-wide messages.
- Ensure your account has sufficient margin for the configured lot size.

**Positions are closed unexpectedly:**
- Check the `max_hold_minutes` setting -- positions are force-closed after this duration.
- Check if the backend went offline (triggers safety shutdown).
- Check if `kill_switch` was activated.

## File Reference

| File | Purpose |
|---|---|
| `DukascopyBridgeStrategy.java` | Main JForex IStrategy implementation |
| `HttpClient.java` | HTTP GET/POST client using java.net.HttpURLConnection |
| `README.md` | This file |
