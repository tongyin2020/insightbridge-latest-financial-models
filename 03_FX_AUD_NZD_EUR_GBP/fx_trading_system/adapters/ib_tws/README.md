# IB TWS Adapter for FX Trading System

This adapter connects to Interactive Brokers Trader Workstation (TWS) or IB Gateway and bridges real-time market data, news, orders, and account information to the Python FastAPI backend running at `http://localhost:8000`.

## Supported Pairs

- AUD/USD
- NZD/USD

## Prerequisites

1. **Interactive Brokers Account** -- either a live or paper trading account.
2. **TWS (Trader Workstation)** or **IB Gateway** installed and running.
3. **Python 3.10+**
4. **Market data subscriptions** -- you need an active forex data subscription in your IB account to receive real-time ticks.

## 1. Setting Up IB TWS or IB Gateway

### Option A: TWS (full desktop application)

1. Download TWS from https://www.interactivebrokers.com/en/trading/tws.php
2. Install and launch TWS.
3. Log in with your IB credentials.

### Option B: IB Gateway (headless, lighter weight)

1. Download IB Gateway from https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
2. Install and launch IB Gateway.
3. Log in with your IB credentials.
4. IB Gateway is preferred for production/server deployments because it uses less memory and has no GUI overhead.

## 2. Enabling API Connections in TWS Settings

1. In TWS, go to **Edit > Global Configuration > API > Settings**.
2. Check **Enable ActiveX and Socket Clients**.
3. Set the **Socket port**:
   - TWS default: **7497** (paper) or **7496** (live)
   - IB Gateway default: **4002** (paper) or **4001** (live)
4. Check **Allow connections from localhost only** (recommended for security).
5. Uncheck **Read-Only API** if you want the adapter to place orders.
6. Set **Master API client ID** to any unused integer (default: 0). The adapter uses client ID 1 by default.
7. Under **Precautions**, you may want to uncheck "Bypass Order Precautions for API orders" for paper trading.
8. Click **Apply** and **OK**.

## 3. Paper Trading Account Setup

1. Log in to the IB Client Portal at https://www.interactivebrokers.com
2. Go to **Settings > Paper Trading Account**.
3. If you do not have a paper account, click **Create** to generate one. It mirrors your live account structure.
4. Your paper account username is typically your live username prefixed with a `D` (e.g., `Dyourusername`).
5. Launch TWS or IB Gateway and log in with the paper trading credentials.
6. Make sure the socket port is set to **7497** (TWS paper) or **4002** (Gateway paper).
7. Reset your paper account balance anytime via the Client Portal.

## 4. Running the Adapter

### Install dependencies

```bash
cd /path/to/fx_trading_system/adapters/ib_tws
pip install -r requirements.txt
```

### Configure environment (optional)

Create a `.env` file in this directory:

```env
IB_HOST=127.0.0.1
IB_PORT=7497
IB_CLIENT_ID=1
BACKEND_URL=http://localhost:8000
```

Or set these as environment variables directly.

| Variable       | Default                  | Description                        |
|----------------|--------------------------|------------------------------------|
| IB_HOST        | 127.0.0.1                | TWS/Gateway host address           |
| IB_PORT        | 7497                     | TWS/Gateway API socket port        |
| IB_CLIENT_ID   | 1                        | Unique client ID for this adapter  |
| BACKEND_URL    | http://localhost:8000     | FastAPI backend URL                |

### Start the adapter

```bash
python ib_adapter.py
```

The adapter will:

1. Connect to TWS/Gateway on the configured host and port.
2. Subscribe to real-time market data for AUD/USD and NZD/USD.
3. Subscribe to IB news feeds (Briefing.com, Dow Jones).
4. Fetch the economic calendar from IB's news providers.
5. Begin a reconciliation loop that syncs positions and account state with the backend every 30 seconds.
6. Poll the backend every 2 seconds for pending order commands (place_order, close_position).

Press `Ctrl+C` to stop the adapter gracefully.

### Test the news classifier standalone

```bash
python news_classifier.py
```

This prints a table of sample headlines with their classified impact level, affected pairs, and category.

## 5. Connecting to the Python Backend

The adapter communicates with the FastAPI backend over HTTP. The backend must expose the following endpoints:

| Method | Endpoint                     | Purpose                                  |
|--------|------------------------------|------------------------------------------|
| POST   | /api/market-data/tick        | Receive real-time bid/ask/last ticks     |
| POST   | /api/news/event              | Receive classified news events           |
| POST   | /api/calendar/events         | Receive economic calendar data           |
| POST   | /api/orders/placed           | Notification when an order is placed     |
| POST   | /api/positions/closed        | Notification when a position is closed   |
| POST   | /api/reconciliation/sync     | Periodic position/account reconciliation |
| GET    | /api/orders/pending          | Fetch pending order commands for the adapter to execute |

The `/api/orders/pending` endpoint should return a JSON array of command objects:

```json
[
  {
    "action": "place_order",
    "pair": "AUD/USD",
    "direction": "BUY",
    "quantity": 25000,
    "stop_loss": 0.6450,
    "take_profit": 0.6550
  },
  {
    "action": "close_position",
    "pair": "NZD/USD"
  }
]
```

## Troubleshooting

- **Connection refused**: Make sure TWS/Gateway is running and the API port matches your config. Check that socket clients are enabled.
- **No market data**: Verify you have an active forex market data subscription in your IB account. Paper accounts inherit subscriptions from the linked live account.
- **Order rejected**: Check TWS for the rejection reason. Common causes are insufficient margin, invalid quantity, or trading permissions not enabled for forex.
- **Client ID in use**: Each connected application needs a unique client ID. If another application is already using client ID 1, change `IB_CLIENT_ID` to a different number.
