# EventAlpha timing recalibration proposal (measured 2024-2025)

All numbers in seconds unless noted. `measured` = event-study percentiles from real intraday data; `proposed` = suggested live value.

## CRYPTO  (tick, `crypto_event_summary_BTCUSDT_20260703T065809Z.csv`)

| event | washout p50/p75 | to_peak p50 | trend_life p75 | move bps p50 | -> min_wait | max_wait | time_stop |
|---|---|---|---|---|---|---|---|
| NFP | 68.0/191.0 | 585.5 | 1533.0 | 54.0 | **70** | **585** | **1530** |
| CPI | 1.0/14.5 | 337.0 | 1650.5 | 91.6 | **5** | **330** | **1650** |
| FOMC | 45.0/146.5 | 163.0 | 1061.8 | 82.7 | **45** | **165** | **1050** |
| ALL | 15.0/129.0 | 422.0 | 1516.0 | 79.7 | **15** | **420** | **1530** |

## FX_EURUSD  (tick, `jforex_event_summary_EURUSD_20260703T073143Z.csv`)

| event | washout p50/p75 | to_peak p50 | trend_life p75 | move bps p50 | -> min_wait | max_wait | time_stop |
|---|---|---|---|---|---|---|---|
| NFP | 9.0/151.8 | 243.5 | 1775.2 | 26.8 | **30** | **240** | **1800** |
| CPI | 1.0/78.0 | 414.0 | 1798.0 | 26.4 | **30** | **420** | **1800** |
| FOMC | 3.0/12.8 | 438.5 | 1717.2 | 23.7 | **30** | **435** | **1800** |
| ALL | 1.0/70.0 | 414.0 | 1789.0 | 25.4 | **30** | **420** | **1800** |

## FX_USDJPY  (tick, `jforex_event_summary_USDJPY_20260703T073144Z.csv`)

| event | washout p50/p75 | to_peak p50 | trend_life p75 | move bps p50 | -> min_wait | max_wait | time_stop |
|---|---|---|---|---|---|---|---|
| NFP | 2.5/119.0 | 656.0 | 1798.2 | 34.3 | **30** | **660** | **1800** |
| CPI | 1.0/35.5 | 740.0 | 1798.5 | 40.4 | **30** | **735** | **1800** |
| FOMC | 3.5/30.2 | 444.5 | 1776.2 | 30.6 | **30** | **450** | **1800** |
| ALL | 1.0/47.5 | 587.0 | 1798.0 | 34.6 | **30** | **585** | **1800** |

## OIL  (5-second, `ibkr_event_summary_WTIUSD_20260703T080444Z.csv`)

| event | washout p50/p75 | to_peak p50 | trend_life p75 | move bps p50 | -> min_wait | max_wait | time_stop |
|---|---|---|---|---|---|---|---|
| NFP | 20.0/82.5 | 625.0 | 1482.5 | 25.5 | **60** | **630** | **1470** |
| CPI | 65.0/207.5 | 620.0 | 1587.5 | 29.9 | **65** | **615** | **1590** |
| FOMC | 50.0/176.2 | 960.0 | 1706.2 | 38.2 | **60** | **960** | **1710** |
| ALL | 45.0/170.0 | 675.0 | 1640.0 | 31.3 | **60** | **675** | **1650** |
