# Dukascopy Eight-Symbol Compatibility Matrix

- generated_at: 2026-06-29T21:49:28.015095+00:00
- project: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest`
- source_jar: `/Users/tongyin/JForex4/libs/demo/4.8.15/jforex-api-4.8.13-sources.jar`
- probe_csv_for_jforex: `EURUSD,USDJPY,BTC,MES,MNQ,ZT,ZN,SR3`
- resolved_probe_targets: `EUR/USD, USD/JPY, BTC/USD, USA500.IDX/USD, USATECH.IDX/USD`

| Logical Symbol | Requested Asset | Mode | Dukascopy Candidate | API Exists | Recommendation |
|---|---|---|---|---|---|
| EURUSD | Spot FX | direct | EUR/USD | yes | can_probe_now |
| USDJPY | Spot FX | direct | USD/JPY | yes | can_probe_now |
| BTC | Crypto spot/CFD | direct | BTC/USD | yes | can_probe_now |
| MES | Micro S&P 500 future | proxy | USA500.IDX/USD | yes | can_probe_as_proxy_only |
| MNQ | Micro Nasdaq future | proxy | USATECH.IDX/USD | yes | can_probe_as_proxy_only |
| ZT | 2Y Treasury future | unsupported | - | no | do_not_route_to_dukascopy |
| ZN | 10Y Treasury future | unsupported | - | no | do_not_route_to_dukascopy |
| SR3 | 3M SOFR future | unsupported | - | no | do_not_route_to_dukascopy |

## Notes

- `EURUSD`: Dukascopy strong fit.
- `USDJPY`: Dukascopy strong fit.
- `BTC`: Depends on demo-market availability and permissions.
- `MES`: Proxy only; index CFD, not CME micro future.
- `MNQ`: Proxy only; index CFD, not CME micro future.
- `ZT`: No clean Dukascopy treasury future mapping in public API.
- `ZN`: No clean Dukascopy treasury future mapping in public API.
- `SR3`: No clean Dukascopy short-rate future mapping in public API.
