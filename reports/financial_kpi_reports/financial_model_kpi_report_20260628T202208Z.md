# InsightBridge Financial Models KPI Report

- generated_at: 2026-06-28T20:22:08.245688+00:00
- base: `/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest`

## Runtime Status

- Runner PID: 17760
- Runner Running: False
- Latest Cycle: 80
- Cycle Status: ok
- Started At: 2026-06-28T20:00:05.054756+00:00
- Finished At: 2026-06-28T20:00:49.585657+00:00
- Duration Seconds: 44.53
- Events In Cycle: 7
- Successful Events: 7
- Failed Events: 0
- Telegram Alerts Enabled: True
- Continuous Runtime: 1d 15h 34m 48s
- System Availability: 100.00%
- Financial AI Platform Score: 99.84/100

## Latest Cycle Reports

- `eventalpha_paper_cpi_20260628T200007Z.json`
- `eventalpha_paper_fomc_20260628T200011Z.json`
- `eventalpha_paper_nfp_20260628T200015Z.json`
- `eventalpha_paper_opec_20260628T200020Z.json`
- `eventalpha_paper_eia_inventory_20260628T200025Z.json`
- `eventalpha_paper_geopolitical_20260628T200029Z.json`
- `eventalpha_paper_liquidity_shock_20260628T200049Z.json`

## New Platform Metrics

1. Continuous Runtime: 1d 15h 34m 48s
2. System Availability: 100.00%
3. Decision Distribution: candidate={"watch": 21, "enter_heavy": 12, "enter_normal": 2} | selected={"enter_heavy": 12, "enter_normal": 2}
4. Decision Reason: selected_top=[('regime', 14), ('severity', 14), ('grade', 14), ('posterior', 14), ('execution_confidence', 14)]
5. Data Quality Score: 100.00/100
6. Learning Status: assets_with_learning=5 | total_updates=60
7. AI Brain Activity: events=7 | candidates=35 | selected=14 | reasons=511
8. Risk Environment: High | score=58.29 | top_regimes=[('liquidity_crisis', 0.1409), ('war_shock', 0.1311), ('central_bank_pivot', 0.1249), ('inflation_shock', 0.1146)]
9. Financial AI Platform Score: 99.84/100
10. Version & Model Health:
   - crypto: healthy | health=99.39/100 | adapter=candidate_only | source=`01_Crypto_BTC_ETH_SOL/eventalpha_adapter.py`
   - fx: healthy | health=99.47/100 | adapter=candidate_only | source=`03_FX_AUD_NZD_EUR_GBP/backend/eventalpha_adapter.py`
   - index: healthy | health=99.47/100 | adapter=index_eventalpha_phase2 | source=`02_StockIndex_IBKR_ES_NQ/eventalpha_adapter.py`
   - oil: healthy | health=98.97/100 | adapter=oil_eventalpha_phase1 | source=`04_WTI_Oil_Futures/backend/eventalpha_adapter.py`
   - rates: healthy | health=99.46/100 | adapter=candidate_only | source=`05_Bond_Treasury/backend/eventalpha_adapter.py`

## Five Financial Models Scorecard

| Asset Model | Candidate Events | Selected Events | Selected Rate | Accepted Executions | Accepted Rate | Avg Rank Score | Avg Execution Confidence | Avg Wait Seconds | Avg Risk Fraction | Top Action | Historical Trades | Historical Avg PnL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| crypto | 7 | 0 | 0.00% | 0 | N/A | 0.7682 | 97.55% | 147.6 | 0.00% | watch | 8 | -10.00% |
| fx | 7 | 0 | 0.00% | 0 | N/A | 0.8615 | 97.88% | 141.6 | 0.00% | watch | 12 | 106.67% |
| index | 7 | 7 | 100.00% | 7 | 100.00% | 0.8290 | 97.87% | 146.7 | 1.61% | enter_heavy | 580 | 0.55% |
| oil | 7 | 7 | 100.00% | 7 | 100.00% | 0.7904 | 95.87% | 156.0 | 1.61% | enter_heavy | 576 | 2.29% |
| rates | 7 | 0 | 0.00% | 0 | N/A | 0.7574 | 97.83% | 143.1 | 0.00% | watch | 16 | 115.00% |

## Asset Details

### crypto

- Candidate Events This Cycle: 7
- Selected Events This Cycle: 0
- Accepted Executions This Cycle: 0
- Average Rank Score: 0.7682
- Average Execution Confidence: 97.55%
- Average Wait Seconds: 147.6
- Average Max Risk Fraction: 0.00%
- Top Action: watch
- Top Candidate Reason: news_semantics:0.55x0.85
- Top Selected Reason: N/A
- Historical Trades Logged: 8
- Historical Avg Entry Confidence: 0.7200
- Historical Avg Wait Seconds: 135.0
- Historical Avg PnL: -10.00%
- Learning Updates: 8
- Avg Memory Edge Delta: 0.0000
- Avg Wait Seconds Delta: 60.0
- Avg Risk Multiplier Delta: 0.0000

### fx

- Candidate Events This Cycle: 7
- Selected Events This Cycle: 0
- Accepted Executions This Cycle: 0
- Average Rank Score: 0.8615
- Average Execution Confidence: 97.88%
- Average Wait Seconds: 141.6
- Average Max Risk Fraction: 0.00%
- Top Action: watch
- Top Candidate Reason: news_semantics:0.58x0.85
- Top Selected Reason: N/A
- Historical Trades Logged: 12
- Historical Avg Entry Confidence: 0.7767
- Historical Avg Wait Seconds: 141.7
- Historical Avg PnL: 106.67%
- Learning Updates: 12
- Avg Memory Edge Delta: 0.0100
- Avg Wait Seconds Delta: 12.7
- Avg Risk Multiplier Delta: 0.0067

### index

- Candidate Events This Cycle: 7
- Selected Events This Cycle: 7
- Accepted Executions This Cycle: 7
- Average Rank Score: 0.8290
- Average Execution Confidence: 97.87%
- Average Wait Seconds: 146.7
- Average Max Risk Fraction: 1.61%
- Top Action: enter_heavy
- Top Candidate Reason: news_semantics:0.55x0.85
- Top Selected Reason: news_semantics:0.55x0.85
- Historical Trades Logged: 580
- Historical Avg Entry Confidence: 0.9742
- Historical Avg Wait Seconds: 146.4
- Historical Avg PnL: 0.55%
- Learning Updates: 12
- Avg Memory Edge Delta: -0.0067
- Avg Wait Seconds Delta: 28.3
- Avg Risk Multiplier Delta: -0.0067

### oil

- Candidate Events This Cycle: 7
- Selected Events This Cycle: 7
- Accepted Executions This Cycle: 7
- Average Rank Score: 0.7904
- Average Execution Confidence: 95.87%
- Average Wait Seconds: 156.0
- Average Max Risk Fraction: 1.61%
- Top Action: enter_heavy
- Top Candidate Reason: news_semantics:0.66x0.85
- Top Selected Reason: news_semantics:0.66x0.85
- Historical Trades Logged: 576
- Historical Avg Entry Confidence: 0.9565
- Historical Avg Wait Seconds: 158.3
- Historical Avg PnL: 2.29%
- Learning Updates: 12
- Avg Memory Edge Delta: 0.0033
- Avg Wait Seconds Delta: 26.7
- Avg Risk Multiplier Delta: 0.0000

### rates

- Candidate Events This Cycle: 7
- Selected Events This Cycle: 0
- Accepted Executions This Cycle: 0
- Average Rank Score: 0.7574
- Average Execution Confidence: 97.83%
- Average Wait Seconds: 143.1
- Average Max Risk Fraction: 0.00%
- Top Action: watch
- Top Candidate Reason: news_semantics:0.48x0.85
- Top Selected Reason: N/A
- Historical Trades Logged: 16
- Historical Avg Entry Confidence: 0.7600
- Historical Avg Wait Seconds: 152.5
- Historical Avg PnL: 115.00%
- Learning Updates: 16
- Avg Memory Edge Delta: 0.0225
- Avg Wait Seconds Delta: 6.2
- Avg Risk Multiplier Delta: 0.0150

## Decision Reasons

- Top Selected Reasons: [('regime', 14), ('severity', 14), ('grade', 14), ('posterior', 14), ('execution_confidence', 14), ('memory_edge', 14), ('cross_asset_alignment', 14), ('wait_seconds', 14), ('macro_direction', 14), ('news_semantics', 14)]
- Top Watch Reasons: [('regime', 21), ('severity', 21), ('grade', 21), ('posterior', 21), ('execution_confidence', 21), ('memory_edge', 21), ('cross_asset_alignment', 21), ('wait_seconds', 21), ('macro_direction', 21), ('news_semantics', 21)]
- Top Enter Reasons: [('regime', 14), ('severity', 14), ('grade', 14), ('posterior', 14), ('execution_confidence', 14), ('memory_edge', 14), ('cross_asset_alignment', 14), ('wait_seconds', 14), ('macro_direction', 14), ('news_semantics', 14)]

## Data Quality

- Data Quality Score: 100.00/100
- Report Coverage: 100.00%
- Candidate Completeness: 100.00%
- Execution Coverage: 100.00%
- Freshness Score: 100.00%

## Learning Status

- Assets With Learning: 5
- Total Learning Updates: 60
- Avg Memory Edge Delta: 0.0058
- Avg Wait Seconds Delta: 26.8
- Avg Risk Multiplier Delta: 0.0030
- Latest Learning Update: 2026-06-27T06:01:01.205263+00:00

## AI Brain Activity

- Events Analyzed: 7
- Candidate Decisions: 35
- Selected Decisions: 14
- Executions: 14
- Reason Paths Evaluated: 511
- Asset Ranking Paths: 35
- Macro Regime Snapshots: 14
- Exit Reviews: 14

## Risk Environment

- Risk Environment: High
- Risk Score: 58.29/100
- Dominant Regime: liquidity_crisis
- Top Macro Regimes: [('liquidity_crisis', 0.1409), ('war_shock', 0.1311), ('central_bank_pivot', 0.1249), ('inflation_shock', 0.1146)]

## Version And Model Health

- crypto: status=healthy | health=99.39/100 | adapter=candidate_only | source=`01_Crypto_BTC_ETH_SOL/eventalpha_adapter.py`
- fx: status=healthy | health=99.47/100 | adapter=candidate_only | source=`03_FX_AUD_NZD_EUR_GBP/backend/eventalpha_adapter.py`
- index: status=healthy | health=99.47/100 | adapter=index_eventalpha_phase2 | source=`02_StockIndex_IBKR_ES_NQ/eventalpha_adapter.py`
- oil: status=healthy | health=98.97/100 | adapter=oil_eventalpha_phase1 | source=`04_WTI_Oil_Futures/backend/eventalpha_adapter.py`
- rates: status=healthy | health=99.46/100 | adapter=candidate_only | source=`05_Bond_Treasury/backend/eventalpha_adapter.py`
