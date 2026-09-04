# PAPER 验收协议

## 目标

在系统正式进入 PAPER 模拟盘长期观察之前，通过一组明确、可复核、可自动检查
的准入条件，把当前实现与配置状态与实盘授权彻底分开。协议本身不构成实盘授
权；通过协议只代表当前证据允许进入 PAPER 观察阶段。

## 准入前提

- canonical 顶层仓库为唯一部署源；任何嵌套或备份副本目录一律不参与运行。
- 全部新增能力默认 opt-in；未显式开启时旧行为保持不变。
- 全部阈值必须由部署方书面配置；系统不会自动校准任何进入下单路径的参数。
- 校准工作台产出的建议只能进入 `AWAITING_HUMAN_REVIEW` 状态；未经人工签字
  不得改写任何在线配置。

## PAPER 观察期

- 观察期最短 10 个交易日。中途出现任一阻断性条件应重新计时。
  **口径说明**：`PaperAcceptanceChecker` 目前按**日历日**计算
  `observation_days`（加密 24/7 无差；债券 / 原油 / 指数 10 个日历日约合
  7 个交易日）。因此对非加密模型，`min_observation_days` 应按
  `ceil(10 交易日 × 7/5)`（即至少 14）配置，或由人工复核确认覆盖 10 个
  交易日；交易日口径的自动计数属于后续工作。
- 观察期内订单只能进入 PAPER 通道；不允许把 PAPER 与 LIVE 通道混用。
  配置 `paper_account_ids` 后，账本内出现白名单外的 `account_id` 或
  `ACKED_LIVE` 回执即 FAIL；未配置时检查器无法自行判定通道，该项不启用。
- 意图账本必须覆盖整个观察期；不允许存在任何长期悬挂（默认创建后 24 小时仍
  处于非终态：`RESERVED` / `SUBMITTED` / `PARTIAL` / `FILLED` / `EXIT_*`）
  且未在 cutoff 前进入终态（`CLOSED` / `CANCELLED` / `REJECTED`）的意图。
  24 小时是日内事件驱动模型的默认值；允许多日持仓的模型（如债券）必须在其
  部署配置里按最长持仓周期显式设置 `hanging_grace_s`，不得沿用默认值。
- 观察期只统计 `created_epoch <= cutoff` 的意图；cutoff 之后新增或更新的
  记录不得用于凑足观察天数。

## 自动化检查（`PaperAcceptanceChecker`）

每次评估返回一份 JSON 报告，包含以下四项检查，任一 FAIL 或任一 UNKNOWN
（在 `strict=True` 时）都会将 `overall` 强制置为 `NOT_READY_FOR_PAPER`：

1. `ledger_observation`：意图账本存在（以只读方式打开），按 cutoff 截断后的
   观察期跨度不少于配置的最小天数，没有长期悬挂的非终态意图，且没有长期
   （默认 1 小时）停留在 `PENDING_BROKER_ACK` 的已提交意图。账本缺少
   `broker_ack_state` 列时返回 UNKNOWN（strict 下阻断）。
2. `event_archive`：`required_events` 全部存在，manifest.json 中的 SHA-256
   校验通过，无篡改、无缺失。
3. `runtime_log_freshness`：运行时日志目录存在，最新文件修改时间不晚于
   cutoff，避免复盘窗口混入未来数据。
4. `upstream_block_cleared`：`upstream_states` 表内没有在 cutoff 之前登记
   且截至 cutoff 仍未解除的 `BLOCKED_BY_UPSTREAM` 状态。

所有检查均为只读，不修改账本、不修改归档、不修改日志目录。

### 已知限制

- `upstream_block_cleared` 只看 `upstream_states` 的当前状态：cutoff 时仍
  阻断、cutoff 之后才解除的情况无法从当前状态表中还原，需结合运行日志
  人工复核。
- 观察天数按日历日计（见上节口径说明）。
- 事件回放器 `EventReplayer` 默认 strict：归档内出现坏 JSONL 行或缺少
  `observed_at_utc` 的行即抛错；只有显式 `strict=False` 才跳过并在
  `skipped_rows` 中计数，且不得用于验收。

## 部署清单（首次启用 broker-ack 检查）

1. 在当前 PAPER 观察期完整结束、且处于维护窗口时部署，不要在观察期中途
   切换代码。
2. 首次启动会对旧账本执行幂等迁移：`ALTER TABLE order_intents ADD COLUMN
   broker_ack_state ... DEFAULT 'PENDING_BROKER_ACK'`。**所有历史行都会被
   填成 `PENDING_BROKER_ACK`**，新检查器会把其中所有 `state != RESERVED`
   且超过 `ack_grace_s` 的历史行判为 FAIL（fail-closed 按设计工作）。
3. 因此迁移后必须先回填历史回执：对照券商成交 / 撤单记录，把已确认的
   PAPER 单批量调用 `IntentLedger.record_broker_ack(intent_id, "ACKED_PAPER")`
   （或相应的 `REJECTED` / `CANCEL_ACKED`），回填操作与 payload 一并留档。
4. 回填完成后再首次运行 `PaperAcceptanceChecker`，并在报告中记录
   `hanging_grace_s` / `ack_grace_s` / `paper_account_ids` /
   `min_observation_days` 的实际取值。

## 监控指标

PAPER 观察期内至少监控以下指标，且必须能在观察期结束时逐日回放：

- 每日新增意图数、终态分布、意图从 `RESERVED` 到终态的时间分布。
- 券商回执状态（`broker_ack_state`）分布与拒单分类计数。
- 上游状态变更时序、每次 `BLOCKED_BY_UPSTREAM` 的持续时长与来源。
- 预交易本地控制拒绝次数（按四类：价格护栏、订单价值、数量、消息数）。
- 校准工作台生成的所有 proposal，包含 IS/OOS 度量与最终状态。

## 异常与回滚条件

出现下列任一情况必须立即暂停 PAPER 观察并回到评审：

- 任一意图长期悬挂在 `RESERVED`，或 `broker_ack_state` 长期停留在
  `PENDING_BROKER_ACK`。
- 拒单类别中出现未映射码，被自动归入 `FATAL`。
- 上游白名单外的来源尝试写入 `set_upstream_blocked` / `clear_upstream`。
- 校准工作台产出的 proposal 被误当作在线配置使用（`applies_to_live` 必须
  始终为 `False`）。
- 运行时日志目录出现晚于 cutoff 的文件，或归档 manifest 校验失败。

## 通过并不等于实盘授权

- 本协议输出 `READY_FOR_PAPER_TRIAL` 或 `NOT_READY_FOR_PAPER`，永远不会
  输出 `READY_FOR_LIVE`。
- 进入实盘的授权必须由人工评审签字，并且需要在协议之外单独维护实盘授权
  记录。
- 任何一次实盘决策都必须至少复核以下三项：观察期数据、当次校准 proposal
  的评审记录、以及最新的运行时状态快照。

## 复核与签字

- PAPER 观察期结束后，运营方需汇总观察期内所有指标与 proposal，形成一份
  可追溯的评审报告，并由至少一名操作员与一名风控成员共同签字。
- 签字文档需在实盘授权前保存到独立的、不可被自动化写入的目录。
