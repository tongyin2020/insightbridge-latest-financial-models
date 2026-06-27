# AUD/USD & NZD/USD 事件驱动短时交易系统

## 系统概述

专为 AUD/USD 和 NZD/USD 设计的事件驱动短时交易系统（10-30 分钟持仓）。

核心特性：
- **人工方向判断 + 模型执行**：你决定做多/做空/暂停，模型负责入场时机、风控和执行
- **30 秒确认机制**：重大消息发布后等 30 秒再确认方向（A 级 30s / B 级 20s / C 级不触发）
- **双券商架构**：Dukascopy（主执行）+ Interactive Brokers（数据+备用）
- **实时技术指标**：SMA、EMA、ADX、ATR、RSI、布林带、VWAP
- **四级接管模式**：正常交易 / 只观察 / 只减仓 / 全部平仓
- **Telegram 告警**：交易信号、Kill Switch、数据断流即时推送

## 架构

```
┌─────────────────────────────────────────────┐
│           React Frontend (:3000)            │
│  Dashboard | 30s确认 | 事件日历 | 风控 | 设置 │
└──────────────────┬──────────────────────────┘
                   │ HTTP/WebSocket
┌──────────────────▼──────────────────────────┐
│         FastAPI Backend (:8000)              │
│  市场数据 | 指标引擎 | 信号引擎 | 事件引擎   │
│  SQLite DB | Telegram 告警 | WebSocket       │
└────────┬────────────────────┬───────────────┘
         │                    │
┌────────▼────────┐  ┌───────▼───────────────┐
│ Dukascopy JForex│  │ IB TWS Adapter        │
│ (Java Adapter)  │  │ (Python ib_insync)    │
│ 主执行通道      │  │ 新闻/日历/备用行情     │
└─────────────────┘  └───────────────────────┘
```

## 快速开始

### 前置条件
- Python 3.10+
- Node.js 18+
- （可选）Twelve Data 免费 API Key
- （可选）Telegram Bot Token

### 一键启动

```bash
cd scripts
./start_all.sh
```

这会同时启动后端（:8000）和前端（:3000）。无 API Key 时自动使用模拟数据。

### 分步启动

```bash
# 1. 启动后端
cd scripts && ./start_backend.sh

# 2. 启动前端（新终端窗口）
cd scripts && ./start_frontend.sh

# 3.（可选）启动 IB 适配器
cd scripts && ./start_ib_adapter.sh
```

### 配置 API Keys

编辑 `backend/.env`：

```env
# Twelve Data（免费注册：https://twelvedata.com）
TWELVE_DATA_API_KEY=your_key_here

# Telegram 告警（找 @BotFather 创建 bot）
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 目录结构

```
fx_trading_system/
├── backend/                  # Python FastAPI 后端
│   ├── main.py              # 主应用（16 个 API + WebSocket）
│   ├── config.py            # 配置管理
│   ├── database.py          # SQLite 数据库层
│   ├── market_data.py       # 市场数据服务（Twelve Data / 模拟）
│   ├── indicators.py        # 技术指标计算引擎
│   ├── signal_engine.py     # 交易信号生成引擎
│   ├── event_engine.py      # 事件引擎（30 秒确认状态机）
│   ├── alert_service.py     # Telegram 告警服务
│   ├── requirements.txt     # Python 依赖
│   └── .env.example         # 环境变量模板
├── frontend/                 # React + Vite 前端
│   ├── src/
│   │   ├── App.tsx          # 主应用（6 页面标签导航）
│   │   ├── context/         # React Context（实时数据分发）
│   │   ├── hooks/           # WebSocket + API 自定义 Hooks
│   │   ├── pages/           # 6 个功能页面
│   │   └── components/      # 可复用组件
│   └── package.json
├── adapters/
│   ├── dukascopy/           # Dukascopy JForex 适配器（Java）
│   │   ├── DukascopyBridgeStrategy.java
│   │   ├── HttpClient.java
│   │   └── README.md
│   └── ib_tws/              # IB TWS 适配器（Python）
│       ├── ib_adapter.py
│       ├── news_classifier.py
│       └── README.md
├── scripts/                  # 启动脚本
│   ├── start_all.sh         # 一键启动全部
│   ├── start_backend.sh     # 启动后端
│   ├── start_frontend.sh    # 启动前端
│   └── start_ib_adapter.sh  # 启动 IB 适配器
├── data/                     # SQLite 数据库文件（自动生成）
└── README.md                 # 本文档
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/health | 系统健康检查 |
| GET | /api/prices/{pair} | 最新价格 + 指标 |
| GET | /api/prices/{pair}/history | 历史价格（可指定分钟数） |
| GET | /api/signals | 近期信号列表 |
| GET | /api/signals/current | 当前实时信号状态 |
| GET | /api/trades | 交易历史 |
| GET | /api/trades/stats | 交易统计（胜率、盈亏等） |
| GET | /api/events | 经济事件日历 |
| GET | /api/events/state | 事件引擎当前状态 |
| GET | /api/settings | 所有设置 |
| PUT | /api/settings/{key} | 更新设置 |
| POST | /api/event/trigger | 手动触发事件模式 |
| POST | /api/event/confirm | 确认方向 |
| GET | /api/system/logs | 系统日志 |
| GET | /api/broker/status | 券商连接状态 |
| WS | /ws | 实时数据推送 |

## 数据流

### 正常交易模式
1. 市场数据服务每 60 秒（API）或 2 秒（模拟）拉取价格
2. 技术指标引擎计算 SMA/EMA/ADX/ATR/RSI/布林带
3. 信号引擎根据方向权限 + 指标 + 事件状态生成信号
4. 信号通过 WebSocket 推送到前端
5. 如连接券商：信号转发给 JForex/TWS 执行

### 事件模式（A 级）
1. 经济日历检测到即将发布的 A 级事件
2. 事件前：停止新开仓
3. 事件发布后 0-30 秒：只观察，不交易
4. 第 30 秒：检查三项确认条件
5. 通过：允许开仓 | 不通过：继续观望

## 实施阶段

### 阶段 1（当前）：研究与仿真
- ✅ 后端 + 前端 + 模拟数据
- ✅ 技术指标计算
- ✅ 信号引擎
- ✅ 30 秒确认机制
- 📋 接入 Twelve Data 真实行情
- 📋 接入经济日历 API

### 阶段 2：小仓位自动执行
- 📋 连接 Dukascopy Demo 账户
- 📋 连接 IB Paper Trading
- 📋 验证真实滑点和执行质量
- 📋 券商对账系统

### 阶段 3：正式运行
- 📋 接入真实账户
- 📋 AlphaFlash 升级（如需要）
- 📋 性能优化和监控
