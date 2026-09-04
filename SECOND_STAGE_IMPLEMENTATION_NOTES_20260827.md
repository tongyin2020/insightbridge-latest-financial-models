# InsightBridge 五金融模型第二阶段实施说明

## 本包定位

本包建立事件驱动交易的安全骨架，不代表策略已经获得可实盘部署资格。仓库缺少可独立复算的五产品原始分钟、逐笔、L1 和 L2 历史档案，因此任何具体冷静期、假突破阈值和持仓上限都必须先在 paper/shadow 模式积累数据，再做严格的前向校准。

## 已实现

- 修复两处回测未来数据泄漏：持仓结束前完整路径不得生成入场特征，early-move 仅能读取入场前数据。
- 非加密 bracket 保护腿绑定 parentId。
- 期货仓位计算纳入合约乘数。
- 下单后保留累计成交数量、均价和首次成交时间，不再把一次即时轮询当作最终状态。
- 加密软止损只按券商确认的成交数量建立。
- Level-2 深度按档位记录；严格假突破模式在缺少深度时 fail closed。
- SQLite 持久化经济意图：确定性 intent ID、账户级 leader lease、跨进程唯一性、重启后去重。
- 年度重大事件预算默认 15 次；同一事件默认只允许一个产品建立经济风险。
- 持仓计时从首次券商确认成交开始；后续分批成交不重置时钟。
- 产品级硬持仓上限暂设为 paper-only 假设，且安全退出条件不能被分数覆盖。
- 可选事件数据档案保存事件 t0、合约元数据、分钟 bar 原始时间、L1、L2 和 SHA-256 清单。
- live 账户风险从 IBKR 账户值和券商持仓读取；关键字段不可用时 fail closed。
- 当前连续亏损按尾部连续亏损计算，不再误用历史最大连亏。

## 仅具备接口或观测能力

- 生命周期模块可以产生 hard-cap、流动性坍塌、反转、数据陈旧等 EXIT 决策，但 runner 尚未把所有 EXIT 决策统一接入可恢复的券商退出状态机。
- L1/L2 归档为轮询快照，不等于完整逐笔或全量 order-book 事件流。
- 账户层 position P&L 百分比尚未从逐仓券商数据可靠计算。
- five-product 共用数据契约已具备落盘基础，但真实历史原始数据仍需采集。

## 实盘放行前必须完成

1. 建立统一退出状态机：提交、部分成交、改价/重试、成交确认、券商零仓位、journal/ledger 关闭。
2. HardStop 的 FLATTEN 和 dead-man 必须真实平仓，并验证网络断开、TWS 重启和进程崩溃恢复。
3. 对非加密 stop/TP 的保护腿成交建立持续订阅和账本闭环。
4. 对加密 IOC 退出持续确认，不得以“已发送”代替“已平仓”。
5. 从券商持仓、未成交单和执行回报重建本地状态，以券商为最终事实源。
6. 采集并封存每个事件的原始 1 秒/5 秒 bar、逐笔、bid/ask 和可得 L2，记录时区、合约、roll、费用与数据版本。
7. 只用前向 walk-forward；所有阈值仅在训练窗校准，测试窗完全冻结。
8. 以净滑点、手续费、延迟和部分成交后的收益分布决定是否保留某产品，不以交易次数或毛收益替代。

## 建议运行顺序

1. `observe-only`：只采集事件和市场数据，不生成订单。
2. `shadow`：生成完整决策和假想订单，不发送券商。
3. `paper`：使用真实券商 paper 订单，验证生命周期与恢复。
4. `micro-live`：每次仅一个产品、最小数量、人工在场，且全部故障演练通过。
5. `limited-live`：年度事件预算仍然硬限制；任何关键数据、时钟或账本不一致均停止新入场并按预案退出。

## 验证入口

- `execution_framework/test_intent_ledger.py`
- `execution_framework/test_position_lifecycle.py`
- `execution_framework/test_event_data_archive.py`
- `execution_framework/test_account_risk_snapshot.py`
- `execution_framework/test_fakeout_live.py`
- `execution_framework/test_pipeline_dryrun.py`
- `execution_framework/test_crypto_spot.py`
- `execution_framework/test_journal_guardian.py`
- `eventalpha_intraday_study/test_causal_replay.py`

