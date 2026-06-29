# Dukascopy Tick Probe

This is the minimal no-trading Dukascopy validation path.

Purpose:
- verify JForex4 can run a local strategy
- verify the strategy can reach the local backend
- verify live ticks can arrive on the Mac terminal

It does **not** place any orders.

## Files

- Strategy source:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/03_FX_AUD_NZD_EUR_GBP/fx_trading_system/adapters/dukascopy/DukascopyTickProbeStrategy.java`
- Build helper:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/build_dukascopy_tick_probe.sh`
- Output JAR:
  - `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/03_FX_AUD_NZD_EUR_GBP/fx_trading_system/adapters/dukascopy/dukascopy-tick-probe.jar`

## Build

```bash
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/build_dukascopy_tick_probe.sh
```

## Start local backend

```bash
bash /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/start_dukascopy_fx_bridge_backend.sh
```

## Check backend before loading strategy

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_dukascopy_fx_bridge_status.py
```

Expected state before JForex loads the probe:
- `backend_api: LIVE`
- `Overall: BACKEND_READY_ADAPTER_IDLE`

## Load in JForex4

Load this JAR in JForex4:

```text
/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/03_FX_AUD_NZD_EUR_GBP/fx_trading_system/adapters/dukascopy/dukascopy-tick-probe.jar
```

Recommended strategy parameters:
- `Backend URL`: `http://127.0.0.1:8001`
- `Pairs CSV`: `AUD/USD,NZD/USD,EUR/USD,USD/JPY`
- `Tick forwarding interval (ms)`: `1000`
- `Status heartbeat interval (ms)`: `10000`

## Verify after starting in JForex4

```bash
python3 /Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/check_dukascopy_fx_bridge_status.py
```

Expected success pattern:
- `connected: True`
- `status: probe_live`
- `account_id:` populated
- `equity:` populated
- `tick ...` lines appearing

If that works, the data path is proven and we can decide later whether to keep using the probe or move back to a richer trading bridge.
