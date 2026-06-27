# WTI v1 — WTI原油事件驱动交易模型

## 架构概览

```
wti_v1/
├── config/
│   └── settings.py          # 所有参数集中配置
├── models/
│   └── core.py              # 数据模型（Bar, Tick, Signal, Position...）
├── app/
│   ├── event_bus.py         # 事件总线（模块解耦核心）
│   └── main.py              # 系统主入口 + 人工控制接口
├── services/
│   ├── risk_service.py      # 风控服务（独立，不可绕过）
│   ├── regime_service.py    # 环境识别（量化 + 人工override）
│   └── signal_service.py    # 信号服务（动态确认逻辑）
├── brokers/
│   └── paper_broker.py      # 模拟经纪商（v1阶段使用）
└── backtest/
    └── engine.py            # 回测引擎（bar-by-bar）
```

## 与原方案书的主要改进

| 方面 | 原方案书 | 本实现 |
|------|----------|--------|
| 确认机制 | 固定30秒等待 | 动态确认：在时间窗口内等待价格行为满足多个量化条件 |
| 环境识别 | 文字描述 | 量化标准（ADX阈值、ATR倍数、具体数值） |
| 止损计算 | 方向性描述 | 基于ATR的动态止损（1.5倍ATR） |
| 人工判断接口 | 概念性描述 | 明确的override API（set_human_override） |
| 风控停手 | 规则列表 | 硬编码不可绕过的守门人 |

## 运行顺序

### 阶段1：安装依赖
```bash
pip install asyncio loguru pandas numpy
```

### 阶段2：配置参数
修改 `config/settings.py` 中的参数，特别是：
- `RISK.account_equity`：你的账户资金
- `RISK.max_risk_per_trade_pct`：单笔风险比例
- `BROKER.mode`：先用 "paper"

### 阶段3：历史验证（建议先做）
```python
from backtest.engine import BacktestEngine, BacktestConfig

config = BacktestConfig(
    start_date="2023-01-01",
    end_date="2024-06-30",
    in_sample_end="2023-12-31",  # 样本内
)
engine = BacktestEngine(config)
# result = await engine.run(bars, events, indicators)
# print(result.summary())
```

### 阶段4：模拟盘运行
```bash
python app/main.py
```

### 阶段5：人工环境控制
在交易过程中，你可以随时调用：
```python
# 判断今天局势不好，停止交易
human_set_regime(system, "blocked", "中东局势严峻", hours=8.0)

# 判断单边趋势形成
human_set_regime(system, "trend", "明显上行趋势", hours=2.0)

# 紧急停止
human_kill_switch(system)
```

## 核心设计原则

1. **风控不可绕过**：`RiskService.check_signal()` 是任何执行的前置条件
2. **人工定义环境，程序负责执行**：`RegimeService.set_human_override()` 是你的判断入口
3. **事件总线解耦**：各模块不直接调用，通过事件通信，便于替换组件
4. **先验证后实盘**：`BacktestEngine` 必须先跑通，且要做样本内外分析
5. **纪律胜过预测**：止损和停手是第一优先级，不是事后弥补

## 下一步（v1.1计划）

- [ ] 接入真实行情源（Tradovate WebSocket 或 IBKR TWS）
- [ ] 接入经济日历API（Trading Economics / Investing.com）
- [ ] 动量衰减检测（持仓中实时监控）
- [ ] 日报生成（每日自动复盘）
- [ ] AUD/USD 模块扩展
