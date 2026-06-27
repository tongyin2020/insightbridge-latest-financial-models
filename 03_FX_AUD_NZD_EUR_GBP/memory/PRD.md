# FX Trading System - AUD/USD & NZD/USD 事件驱动短时交易系统

## 项目概述
基于用户提供的交易模型方案，构建专业的外汇短时交易系统APP，支持AUD/USD和NZD/USD货币对的事件驱动交易策略。

## 用户画像
- **主要用户**: 个人外汇交易者
- **使用场景**: 高杠杆(100-200倍)短时交易(10-30分钟)
- **平台**: Dukascopy Bank (瑞士银行), Interactive Brokers
- **核心需求**: 宏观方向判断 + 结构化事件确认 + 严格风控

## 技术架构

### 后端 (FastAPI + MongoDB)
- `server.py` - 主服务（API路由 + 数据服务）
- `event_response_engine.py` - 5阶段事件响应状态机
- `execution_gate.py` - P0-P6优先级执行闸门
- `strategy_monitor.py` - 策略失效检测器
- `database.py` - MongoDB CRUD
- MongoDB持久化 + Telegram推送 + GPT-5.2 AI分析

### 前端 (React)
- `App.js` - 全功能交易仪表板
- Recharts图表 + Phosphor Icons + 深色主题
- 中文界面

### 数据库 (MongoDB)
- Collections: settings, telegram_config, alert_history, ai_analyses, backtest_results

---

## 已实现功能 ✅

### Phase 1 - MVP (2026-03-31)
- 实时行情与技术指标 (SMA/ADX/RSI/ATR/Bollinger)
- 事件引擎30秒确认机制
- 高级风险控制系统 (多层止损/日限/恶化检测/三阶段保护)
- AI市场分析 (GPT-5.2)
- 历史回测 (50+交易)
- 蒙特卡洛模拟
- 参数网格搜索优化 (3125+组合)
- 经济日历/宏观驱动/系统状态

### Phase 2 - Telegram + MongoDB (2026-03-31)
- Telegram风险警报 (Bot: @ty0023_bot, 已连接)
- MongoDB数据持久化

### Phase 3 - 核心引擎升级 (2026-04-01) ✅ NEW
基于用户提供的详细改进文档实施

**1. 事件响应引擎 (Event Response Engine)**
- 5阶段状态机: IDLE → EVENT_DETECTED → IMPULSE_PHASE → LIQUIDITY_REBUILD → DIRECTION_CONFIRM → READY/INVALID
- 品种差异化配置:
  - AUD/USD: max_wait=90s, impulse_vol_threshold=1.8x, 需二次推动确认
  - NZD/USD: max_wait=90s, impulse_vol_threshold=1.5x, 需二次推动确认
- 替代固定30秒等待，等待"市场结构完成重定价"

**2. 执行闸门 (Execution Gate)**
- P0-P6优先级裁决层:
  - P0: Kill Switch / 系统安全(过期报价)
  - P1: 市场恶化接管
  - P2: 冷却期/恢复状态
  - P3: 事件就绪检查
  - P4: 组合限制(连亏/日限)
  - P5: 时间止损(40分钟)
  - P6: 信号审批
- 品种差异化仓位管理:
  - AUD/USD: 0.3%基础风险, 0.7x乘数
  - NZD/USD: 0.25%基础风险, 0.6x乘数
- Regime风险乘数: NORMAL=100%, TREND=100%, RANGE=80%, EVENT=60%, UNSTABLE=0%

**3. 策略失效检测器 (Strategy Monitor)**
- 连亏检测: AUD/USD 4笔降档→6笔冻结, NZD/USD 3笔降档→5笔冻结
- 恶化频率: 1天≥3次触发→当日停机
- 渐进恢复: COOLDOWN → 30% → 50% → 75% → 100%
- 手动解冻功能

**4. 双信号确认**
- Breakout + 波动率放大(Vol Expansion)同时成立才提高置信度
- 无波动率放大时信号降权30%

**5. 特征引擎 (Feature Engine)**
- vol_ratio (1分钟/5分钟波动率比)
- spread_ratio (当前/基线点差比)
- trend_score_5m (5分钟方向强度 -1~1)

---

## 未来任务

### P1 - 实时数据接入
- Twelve Data API (或Dukascopy/IB数据源)
- 替换模拟数据

### P1 - 券商API对接
- Dukascopy JForex API
- Interactive Brokers TWS API
- 实时订单执行

### P2 - 代码重构
- server.py拆分为模块化路由
- App.js拆分为独立React组件

### P2 - 增强退出机制
- 结构化双退出: 时间退出 + 结构退出(波动衰减/动能消失)
- 取较早者

---

## API 端点

### 核心
- GET /api/health
- GET /api/prices/{pair_key}
- GET /api/signals/current
- GET /api/events
- GET /api/settings
- PUT /api/settings/{key}

### 事件响应引擎
- GET /api/event-response/status
- POST /api/event-response/trigger
- POST /api/event-response/reset

### 执行闸门
- GET /api/execution-gate/status
- POST /api/execution-gate/evaluate

### 策略监控
- GET /api/strategy-monitor/health
- POST /api/strategy-monitor/record-trade
- POST /api/strategy-monitor/unfreeze

### 特征
- GET /api/features/{pair_key}

### 风控
- GET /api/risk/status
- GET /api/risk/capital-protection
- GET /api/risk/monte-carlo

### AI & 回测
- POST /api/ai/analysis
- GET /api/backtest/stats

### Telegram
- GET /api/telegram/status
- POST /api/telegram/config
- POST /api/telegram/test
