# Execution Framework — 事件后右侧确认执行框架

这是把仓库从"AI 研究系统"升级为"可交易系统"的执行层。它实现了
"重大事件后不抢第一秒 → 冷静期 → ATR 噪声衰减 → K线实体突破 → 影线/成交量/点差/滑点/时段过滤
→ 合约解析锁定 → 风险约束算手数 → 带保护单的 dry-run 下单 → 成交确认 → 结构化日志"的完整闭环。

> ⚠️ 默认 **dry-run（不真实发单）**。真实下单需显式 `dry_run=False` 且 `confirm_live=True`，
> 并且只在 IBKR 模拟盘（端口 7497 / DU 开头账号）验证通过后再考虑。

## 为什么新增这一层（对应技术审计的结论）

审计发现：仓库里**好的共享风控**（`shared_risk_guard.py` 的 `HardStopController`、
`shared_quant_core.py` 的 `CorrectPositionSizer` / `StrategyEvaluator`）**没有被任何模型调用**，
而五个模型大多跑在仿真/随机种子数据上。本框架做两件关键事：

1. **把共享风控设为下单前的强制串联门** —— 信号产生后必须依次通过
   `HardStopController.check()`（日亏/连亏/延迟/点差爆炸等 8 条硬规则）和
   `CorrectPositionSizer.compute()`（风险预算/流动性/滑点/延迟/尾部五约束取最小）。
   **手数由风险约束算出，不再写死 `quantity=1`。**
2. **修正最初骨架里 5 个会导致错误成交或丢机会的实盘缺口**（见下）。

## 相对最初骨架修正的问题

| # | 原骨架问题 | 本框架的修正 |
|---|-----------|-------------|
| 1 | 裸市价单 `MKT`，滑点过滤形同虚设 | 改为 **marketable limit**（参考价 ± N tick 保护价），滑点检查真正约束成交价 |
| 2 | 括号单不是真正 OCA，止损成交后另一腿变裸单 | 用 `ocaGroup + ocaType=1` 组成真正 OCA bracket（含可选止盈腿）|
| 3 | 信号成立立即 `active=False`，下单失败永久丢机会 | 改为 `confirmed_pending`；只有 `mark_filled()`（成交确认）后才关闭事件 |
| 4 | 无重复下单保护 | `client_ref` 去重 + 单品种"在途/持仓"互斥锁 |
| 5 | `base_atr` 取事件当根（已被首冲击污染）| 改用**事件前窗口均值**；ATR 出现新高时重置确认，避免"假峰值"过早进场 |
| 6 | 实体突破无成交量确认 | 新增"突破K线量 ≥ 前N根均量×倍数"门槛 |
| 7 | 无交易时段过滤 | 每品种可配 `session_start/end_utc`（指数/国债默认只在欧美主时段）|
| 8 | 点差/滑点统一用 bps（对国债/SOFR 不合理）| 改为按品种 **tick 数**表达上限 |
| 9 | 用 `symbol="MES"` 直接下单（CONTFUT 风险）| `IBKRContractResolver`：`reqContractDetails → 选近月/主力 → 锁 conId → 缓存`，**未锁定 conId 拒绝下单** |

## 模块

- `event_right_side_engine.py` — 右侧确认信号闸门（6 层过滤，纯判定）。
- `ibkr_contract_resolver.py` — 合约唯一解析（禁用 CONTFUT 下单）。
- `ibkr_order_manager.py` — marketable-limit + OCA bracket + 成交确认 + 去重，默认 dry-run。
- `right_side_pipeline.py` — 把以上 + 共享硬风控 + 仓位计算器串成闭环，并产出 KPI。
- `test_pipeline_dryrun.py` — 离线自检（无需连 IBKR）。

## 8 个核心品种（先跑这些，别一上来跑 26 个）

FX：`EURUSD` `USDJPY` ｜ Index：`MES` `MNQ` ｜ Treasury：`ZT` `ZN` ｜ Rates：`SR3` ｜ Crypto：`MBT`

每个品种的冷静期、ATR 衰减阈值、实体/影线比等都是**经验先验初值**，
**必须用 IBKR 模拟盘拉到的真实 1 分钟/tick 数据做 walk-forward 校准**，
并用 `StrategyEvaluator` 跑 IS/OOS 过拟合检查后再定参。

## 快速验证

```bash
python3 execution_framework/test_pipeline_dryrun.py
```

预期输出：冷静期 HOLD → ATR 衰减确认 → 实体突破 → dry-run 下单意图（手数由风险约束算出）
→ 成交确认 → KPI 报告。

## 接入真实模拟盘（示意，需自行连接 ib_insync）

```python
from ib_insync import IB
from execution_framework.right_side_pipeline import RightSidePipeline

ib = IB(); ib.connect("127.0.0.1", 7497, clientId=11)   # 7497 = 模拟盘
pipe = RightSidePipeline(ib=ib, dry_run=True, equity=50000,
                         log_path="reports/right_side_runs/mnq.log")

pipe.on_event("MNQ", "CPI", event_time, df_1min)          # 新闻/日历识别到事件
res = pipe.step("MNQ", now, df_1min, bid=b, ask=a,        # 每分钟评估
                account_state={"equity": 50000, "consec_losses": 0,
                               "daily_pnl_pct": 0.0, "feed_lag_ms": 80})
if res["status"] in ("BUY", "SELL"):
    state = pipe.confirm_fill("MNQ", res["client_ref"])   # 拿到回报后推进状态
```

真实发单前请把 `dry_run=False` 且对 `step(..., confirm_live=True)`，并务必先在模拟盘充分回放。

## 待办（第三优先，尚未实现）

- IBKR 错误码处理（200/201/1100 等）、断线重连、`reqExecutions`/`reqOpenOrders` 对账。
- 用真实模拟盘数据对 8 品种做 walk-forward + IS/OOS 过拟合检查后再定参。
- 主力合约按 OI/成交量选择（当前默认近月）。
