# 第四阶段实现说明（2026-09-03）

## 总体安全边界

- 本阶段代码仅修改 canonical 顶层仓库；未修改任何
  `_duplicate_backup_20260824`、嵌套 `Oil-Trading-System` 或
  `Bond-Trading-System` 复制目录。
- 全部新增能力默认 opt-in。新增的三个模块（事件回放、校准工作台、
  PAPER 验收）在模块顶部注释与运行时属性上明确 read_only、不发送订单、
  不改配置、不做网络调用。
- 校准建议不会写入任何在线配置。所有 proposal 状态默认为
  `AWAITING_HUMAN_REVIEW`，且 `applies_to_live=False`。
- 上游可信来源为可选白名单。未提供时保留旧行为；提供后即 fail closed。
- 未做盈利声明，未做 synthetic/simulated 回退。

## 1. 只读事件回放器

### 已实现

- `execution_framework/event_replayer.py`：
  - 读取 `EventDataArchive` seal 出的 metadata.json 与 manifest.json；
  - 对 manifest 中每个文件做 SHA-256 校验，任一失败即抛 `ValueError`；
  - 拒绝 `metadata.synthetic=True` 与命中 SYNTHETIC_MARKERS 的 `source`；
  - `EventReplayer.load_event(event_id, symbol, cutoff_utc)` 返回不可变
    `ReplayView`；
  - `ReplayView.bars/l1/l2/trades/broker` 每次都以 UTC 强制过滤
    `observed_at_utc <= cutoff`；
  - cutoff 必须 timezone-aware；无 tz 立即 `ValueError`；
  - 类属性 `read_only=True`、`may_submit_orders=False`；
  - 顶层 `verify_manifest(event_dir)` 独立可调用，返回
    `{status, files_checked, mismatches}`；
  - 模块不 import broker/order manager，未进行网络调用。

### 仅具备接口

- 目前只支持 EventDataArchive JSONL 结构；MBO 与其它 archive 类型未实现。

### 尚未实盘闭环

- 未接入真实历史归档；测试用 tmp 目录归档验证。

## 2. 校准工作台

### 已实现

- `execution_framework/calibration_workbench.py`：
  - `CalibrationWorkbench.evaluate` 接收纯 dict 样本与参数网格；
  - 按 `ts` 升序切 70/30 IS/OOS；
  - 使用可注入的 `score_fn`；结果强制 finite 且非负 n；
  - 通过条件必须全部满足：IS n≥30、OOS n≥15、IS sharpe>0、OOS sharpe>0、
    `|IS_sharpe / max(OOS_sharpe, 1e-9)| ≤ 3`、IS 与 OOS mean_bps 同号；
  - 输出包含 `proposal_id`（SHA-256 摘要）、`algo_version`、
    `generated_at_utc`、`sample_window`、`is_metrics`、`oos_metrics`、
    `recommended_params`、`status`、`approval` 与 advisory 标志；
  - status 取值：`PROPOSED`、`REJECTED_INSUFFICIENT_SAMPLE`、
    `REJECTED_OVERFIT`、`REJECTED_SIGN_FLIP`；
  - `approval={"state":"AWAITING_HUMAN_REVIEW","approved_by":None,
    "approved_at_utc":None}`；
  - `is_advisory_only=True`、`applies_to_live=False`；
  - `evaluate` 本身不落盘；`write_proposal` 原子写
    `out_dir/proposals/{proposal_id}.json`，已存在不覆盖。

### 仅具备接口

- 未内置任何 score_fn；调用方必须显式提供纯函数。

### 尚未实盘闭环

- 建议永远不进入下单路径；实盘参数必须走独立的人工评审签字流程。

## 3. PAPER 验收协议

### 已实现

- `execution_framework/paper_acceptance.py`：
  - `PaperAcceptanceChecker` 只读评估四项：ledger 观察期与悬挂意图、
    event archive manifest、runtime log freshness、
    upstream_states 的 BLOCKED_BY_UPSTREAM 是否跨越 cutoff；
  - 任一 FAIL 或（`strict=True` 下）任一 UNKNOWN → `overall="NOT_READY_FOR_PAPER"`；
  - 永远不返回 `READY_FOR_LIVE`，最优结果为 `READY_FOR_PAPER_TRIAL`；
  - `write_report(path)` 原子写 JSON；
  - `read_only=True`、`may_submit_orders=False`。
- `docs/PAPER_ACCEPTANCE_PROTOCOL.md`：中文协议，覆盖目标、准入前提、
  最短 10 交易日观察期、自动化检查、监控指标、异常回滚条件、
  “通过 ≠ 实盘授权”与人工签字要求。

### 仅具备接口

- 目前只从 SQLite 意图账本、事件归档与日志目录读取信息；未接入交易所或
  券商侧独立健康报告。

### 尚未实盘闭环

- 协议输出必须结合人工评审证据方可推进；不构成自动化实盘授权。

## 4. 上游可信来源白名单与券商回执占位

### 已实现

- `execution_framework/bounded_autonomy_rules.py`：
  - `BoundedAutonomyController` 新增可选参数
    `trusted_upstream_sources: Optional[set[str]]`；未提供保持旧行为；
  - `set_upstream_blocked` / `clear_upstream` / `_set_upstream` 增加
    `source: Optional[str]` 关键字参数；
  - 白名单已设置时，缺 source 或 source 不在白名单即 `ValueError`
    fail closed；
  - `upstream_states` 表通过 PRAGMA table_info + 幂等 ALTER TABLE 加入
    `source` 列；
  - 审计记录携带 `source` 字段。
- `execution_framework/intent_ledger.py`：
  - `order_intents` 新增 `broker_ack_state TEXT NOT NULL DEFAULT
    'PENDING_BROKER_ACK'` 与 `broker_ack_payload TEXT`，通过幂等 ALTER
    TABLE 迁移旧库；
  - 新方法 `record_broker_ack(intent_id, ack_state, payload_json)`：
    仅允许 `PENDING_BROKER_ACK / ACKED_LIVE / ACKED_PAPER / REJECTED /
    CANCEL_ACKED / CANCEL_REJECTED`，其它 `ValueError`；
  - `record_broker_ack` 不改变 `state` 字段；
  - `get_intent` 返回新列。

### 仅具备接口

- broker ack 目前只是账本占位；未与真实券商撤单/回执 API 对接。
- upstream 白名单只做接受方校验；未见证来源签名或多源交叉。

### 尚未实盘闭环

- 券商回执状态需要独立的、可信的调用方写入；未接真实券商回报通道。

## 5. 一体化测试

### 已实现

- `execution_framework/test_stage4_end_to_end.py`：
  - 使用 `EventDataArchive` 打包 → seal → `EventReplayer` 加载，验证
    cutoff 严格过滤事件后 trade；
  - 两个 algo_version 分别喂 `CalibrationWorkbench`：一个 PROPOSED
    （`AWAITING_HUMAN_REVIEW`），一个 REJECTED_OVERFIT；
  - 构造 SUBMITTED 意图账本，`PaperAcceptanceChecker` 输出
    `overall="READY_FOR_PAPER_TRIAL"`；
  - 反面用例：required_event 缺失时输出
    `overall="NOT_READY_FOR_PAPER"`。

## 测试结果

- 新增定向测试：
  `pytest -q test_event_replayer.py test_calibration_workbench.py
  test_paper_acceptance.py test_intent_ledger.py
  test_bounded_autonomy_rules.py test_stage4_end_to_end.py`
  — 共 `37 passed`（event_replayer 6 + calibration 6 +
  paper_acceptance 8 + intent_ledger 8 + bounded_autonomy 7 +
  stage4 e2e 2）。
- `execution_framework` 全量目标测试：`pytest -q` — `113 passed`。
- canonical 仓库 Python 编译检查（排除三个复制目录）：
  `compiled=329 errors=0`。
- `git diff --check` 通过，无空白警告（exit=0）。

## 新增文件

- `execution_framework/event_replayer.py`
- `execution_framework/test_event_replayer.py`
- `execution_framework/calibration_workbench.py`
- `execution_framework/test_calibration_workbench.py`
- `execution_framework/paper_acceptance.py`
- `execution_framework/test_paper_acceptance.py`
- `execution_framework/test_stage4_end_to_end.py`
- `docs/PAPER_ACCEPTANCE_PROTOCOL.md`
- `FOURTH_STAGE_IMPLEMENTATION_NOTES_20260903.md`

## 修改文件

- `execution_framework/bounded_autonomy_rules.py`
- `execution_framework/intent_ledger.py`
- `execution_framework/test_bounded_autonomy_rules.py`
- `execution_framework/test_intent_ledger.py`

## 剩余风险

1. 事件回放器只处理 EventDataArchive 结构；未验证真实历史行情、真实
   MBO 深度或多经纪商归档场景。
2. 校准工作台不校准任何进入下单路径的阈值；`applies_to_live=False`
   仅是软契约，仍依赖调用方遵守。
3. PAPER 验收协议为只读判断，不能替代人工评审、券商风控或交易所控制；
   `overall` 输出上限仅为 `READY_FOR_PAPER_TRIAL`。
4. broker_ack_state 只是账本占位。真实券商回报通道未接入；
   `PENDING_BROKER_ACK` 长期停留只能靠外部监控发现。
5. 上游白名单未内置来源真实性校验（无签名、无内容哈希、无多源交叉），
   只能拒绝白名单外的写入；对被伪装成受信来源的写入无防护。
6. 全部新增数据库迁移采用幂等 ALTER TABLE，未做真实跨机、跨进程并发
   长跑压力测试；SQLite 定位仍是单机持久化边界。
7. 校准 proposal 采用文件系统原子写并禁止覆盖，但未做防篡改签名；
   proposal 目录仍需要在部署方侧受权限保护。
