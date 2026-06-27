宏观交易5-Agent系统 (Macro Trading CrewAI)
==========================================
文件位置：DSW云端 /mnt/workspace/ 以及 OSS 备份

主要文件：
  - macro_trading_agents.py  (5个Agent定义)
  - macro_trading_crew.py    (Crew编排)
  - macro_trading_tasks.py   (Task定义)
  - macro_live_trader.py     (实盘执行)
  - tools/macro_trading_tools.py
  - tools/macro_event_engine.py

5个Agent：
  1. MacroEventScanner    — 宏观事件扫描 (FOMC/CPI/NFP)
  2. RegimeDetectionAgent — 市场状态识别 (PANIC/BREAKOUT)
  3. EntryTimingAgent     — 精准入场 (FakeSpikeAnalyzer + OBI + GARCH)
  4. ConvictionSizerAgent — 信念仓位计算 (Kelly公式)
  5. ExitGuardAgent       — 离场守卫 (Kalman + 流动性 + 波动率断路器)

OSS备份路径：oss://insightbridge-oss/insightbridge/
