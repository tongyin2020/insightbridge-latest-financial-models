# InsightBridge Financial Agent System

独立的事件驱动 AI 代理层，用于观察、研判、并逐步提高 5 个金融交易机器人。

## 安全默认

- `AGENT_OBSERVE_ONLY=1`（默认）—— 只读本地日志，不连接 IBKR。
- `AGENT_EXECUTION_ENABLED=0`（默认）—— 即使研判子图给出建议，也不会实际下单。
- 执行桥只在 `execution_enabled=True` 且 `observe_only=False` 时才会调用 `SignalRouter`。

## 架构

```text
Gatekeeper (MacroMonitor) → CRISIS_AWAKEN → LangGraph crisis subgraph
  ├─ macro_agent        宏观/地缘
  ├─ technical_agent    技术面/时序
  ├─ critic_agent       红队批判
  └─ risk_agent         极端尾部风险 / 头寸管理

consensus → ExecutionBridge (stage/live) → ReflectionAgent
```

## 快速开始

```bash
# 安装依赖
pip install -r agent_system/requirements.txt

# 观察模式运行
python3 agent_system/run_agent_system.py

# 同时生成复盘报告
python3 agent_system/run_agent_system.py --run-reflection
```

## macOS 定时运行 (launchd)

```bash
cd agent_system/scripts
./install_launchd.sh
```

## 环境变量

| Variable | Default | 说明 |
| --- | --- | --- |
| `AGENT_BASE` | repo root | 数据和报告的根目录 |
| `AGENT_OBSERVE_ONLY` | `1` | `0` 关闭观察模式 |
| `AGENT_EXECUTION_ENABLED` | `0` | `1` 才允许连接执行 |
| `AGENT_CRISIS_THRESHOLD` | `0.55` | Gatekeeper 危机阈值 |
| `AGENT_USE_LLM` | `0` | `1` 启用 NVIDIA/LLM 总结 |
| `AGENT_LLM_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | LLM 模型 ID |
| `AGENT_LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | LLM endpoint |

## 测试

```bash
python3 -m pytest agent_system/tests/test_agent_system.py -v
```
