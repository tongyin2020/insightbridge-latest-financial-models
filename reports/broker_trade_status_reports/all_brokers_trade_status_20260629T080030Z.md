InsightBridge All Brokers Trade Status
============================================================
base: /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest
generated_at: 2026-06-29 08:00:22 UTC
------------------------------------------------------------
[IBKR | Interactive Brokers]
connection: ATTENTION | 
broker_open_positions: N/A
journal_open_trades: 0
journal_closed_trades: 0
journal_total_closed_pnl_abs: 0.00
open_trade_details: none
recent_closed_trade_details: none
live_broker_positions: none
------------------------------------------------------------
[Dukascopy | Swiss FX]
connection: LIVE
adapter_status: probe_live
account_id: 3629120
equity: 10000.0
last_seen: 2026-06-29T08:00:25Z | age=5s
configured_pairs: AUD/USD, NZD/USD, EUR/USD, USD/JPY, GBP/USD, AUD/JPY, NZD/JPY
open_positions: 0
closed_trades_in_backend_memory: 0
closed_total_pnl_pips: 0.0
open_position_details: none
recent_closed_trade_details: none
------------------------------------------------------------
Interpretation
------------------------------------------------------------
If open_trade_details or open_position_details is none, that broker currently has no real live trade open.
If recent_closed_trade_details is none, that broker has no recorded completed trade yet in the currently connected journal/backend memory.
IBKR closed trade truth comes from local SQLite trade journal data.db.
Dukascopy trade truth comes from the local FX backend memory and broker-position bridge.
