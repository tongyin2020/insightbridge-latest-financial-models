# 复核修复清单（2026-08-27 第二轮）

本文件由复核方生成，记录对第二阶段安全改造包的 14 项修复与验证结果。
原始包文件未删除；所有修改就地完成，文件级 SHA-256 见文末清单。

## 修复内容

| # | 级别 | 文件 | 问题 | 修复 |
|---|------|------|------|------|
| 1 | P0 | execution_framework/ibkr_order_manager.py | `cancel_all_for` 按 orderRef "SYMBOL-" 前缀匹配；启用 intent ledger 后 client_ref 为 32 位哈希，紧急撤单静默失效 | 新增 client_ref→trade 登记表，以 orderId/permId 为主键撤单；断线重连后兜底按合约品种扫描 openTrades；orderRef 仅兼容旧票据 |
| 2 | P0 | execution_framework/ibkr_order_manager.py | 成交确认/撤单全部依赖 orderRef，而 IBKR 文档标注 orderRef 仅面向机构客户 | `poll_fill` 改为 `_find_parent_trade`：登记 trade 对象 → orderId 扫描 → orderRef 最后兜底 |
| 3 | P0 | execution_framework/position_lifecycle.py | `upsert_broker_fill` 用 `max(remaining, cumulative)`，部分平仓后入场腿更新会把已平数量"复活" | 新增 `cumulative_exit_quantity` 字段；remaining = filled − exited；退出累计回报取单调最大值 |
| 4 | P1 | eventalpha_core/advanced/escape_engine.py | 硬持仓上限两处独立实现（lifecycle monitor 与 escape config），可能漂移 | `escape_decision` 新增 `hard_cap_breached` 参数：显式传入时以 PositionLifecycleMonitor 为唯一权威；None 保持旧行为兼容 |
| 5 | P1 | execution_framework/ibkr_order_manager.py | 软止损平仓价 `round(buf, 2)`，对 tick=0.001 的 SOL 产生非法价格 | 新增 `_round_to_tick`，按合约 tick_size 取整；tick_size 随 ticket/软止损登记传递 |
| 6 | P1 | execution_framework/intent_ledger.py | `advance_intent` 无状态迁移表，接受 FILLED→SUBMITTED 等倒退迁移 | 新增 `INTENT_TRANSITIONS` 白名单；同状态幂等允许；终态不可离开 |
| 7 | P2 | 全包 | 补丁不自包含，无法复现"405 文件语法检查"；test_fakeout_live 缺依赖时失败 | 新增本 manifest：列明补丁文件哈希与所需基础模块清单（见下） |
| 8 | P0 | execution_framework/intent_ledger.py + right_side_pipeline.py + run_tws_continuous.py | leader 租约无 fencing token：进程停顿超过 TTL 后租约被接管，旧进程苏醒仍可能发单（split-brain） | `execution_leases` 新增 `fencing_epoch` 列（ALTER TABLE 就地迁移旧库，并发初始化带重试）；acquire 时 epoch+1、renew 不变；新增 `current_fencing_token`/`check_fencing`（BEGIN IMMEDIATE 事务内比对 owner+epoch+未过期）；管线 `configure_lease_guard()` 在取得租约后固定 token，`step()` 每次下单前校验，失配即拒单+撤销意图+halt；runner 取得租约后启用守卫，token 读取失败则安全退出 |
| 9 | P0 | execution_framework/position_lifecycle.py + right_side_pipeline.py | `PositionLifecycleMonitor.positions` 只在内存：进程崩溃/重启后持仓时钟清零，硬封顶可被重启绕过 | 新增可选 `persist_path`（SQLite，`position_states` 表，WAL）：register/upsert/exit 提交/退出确认每次状态变更写穿；`restore()` 启动时读回，broker_fill_time 原样保留、封顶时钟跨崩溃连续；管线默认落在 safety_db 旁的 `.lifecycle.db`（可用 `lifecycle_db` 覆盖） |
| 10 | P1 | execution_framework/event_right_side_engine.py | 交易时段写死 UTC（MES/MNQ RTH 13:30–20:00 UTC），事件锚定美东时间，夏令时切换整体漂移一小时——冬季 8:30 ET 的 CPI（13:30 UTC）正压在错误的 MES session 边界上 | `AssetRule` 新增 `session_tz`/`session_start_local`/`session_end_local`（IANA 时区，默认 America/New_York），`_in_session` 优先按交易所本地时间判断、夏令时自动跟随；`*_utc` 字段保留兼容旧配置；MES/MNQ 改 9:30–16:00 ET（RTH），ZT/ZN/SR3 改 3:00–16:00 ET（保持夏季窗口不变） |
| 11 | P1 | execution_framework/trade_journal.py + right_side_pipeline.py | `pnl_abs` 只是价格点数 × 数量：不含合约乘数与费用，跨产品加总混单位，R 倍数全是毛 R，shadow 阶段绩效统计被系统性高估 | `TradeRecord` 新增 `multiplier`/`fee_per_side`；平仓时产出货币口径 `pnl_gross_abs`/`fee_total`/`pnl_net_abs` 与净 R（`r_multiple_net` = 净盈亏 ÷（初始货币风险+双边费用））；旧列 `pnl_abs`/`r_multiple` 语义不变，旧库 ALTER 迁移、旧行按乘数 1/费用 0 退化；`stats()` 新增 `avg_r_net`/`total_pnl_net_abs`/`total_fees`；管线新增 `contract_fees` 配置并按 symbol 查表写入 |
| 12 | P1 | execution_framework/run_tws_continuous.py | 主循环固定 60s 轮询：与'信息约 5 分钟内被吸收'的核心证据不匹配，右侧确认窗口和硬封顶/软止损退出系统性迟到；全程高频又会在空闲态对 TWS 空转 | 新增 `_needs_fast_poll`（模块级，可测）：存在活跃事件窗口/在途订单/未平仓持仓/活跃软止损时切 `--fast-interval`（默认 2s，建议 1–5s）高频档，LEARN 等待态降回 `--interval`（默认 60s）；档位切换落日志 |
| 13 | P1 | execution_framework/event_right_side_engine.py | DEFAULT_RULES 未见 WTI/CL 入场规则（④号产品），生命周期却有 COMMODITY 硬封顶——五模型实际只有四个接线 | 新增 CL 规则（COMMODITY，tick 0.01 = $10/手，RTH 9:00–14:30 ET，冷静期 10/等待 45，阈值为未验证先验待 shadow 校准）；主仓库 enabled_symbols 需包含 CL 才会真正下单（已在规则注释与 manifest 标明） |
| 14 | P1 | execution_framework/negative_control.py（新增） | 冷静期后突破进场与'信息约 5 分钟内被吸收'证据存在张力，该 edge 从未被验证 | 负对照 harness：把封存事件档案逐 bar 回放给真实引擎取方向，同一入场时点/同一止损距离同时算多/空两条腿 R，配对统计 diff = R_signal − (R_long+R_short)/2（随机方向零假设下期望为 0），符号翻转置换检验给 p 值，verdict ∈ edge_supported / edge_challenged / insufficient_evidence；只消费档案观测、不造价格、不碰券商；待 shadow 档案积累后直接运行 `python3 negative_control.py <archive_root>` |

## 新增/更新测试

- `execution_framework/test_review_fixes.py`（新增）：orderId 匹配（无 orderRef）、哈希 client_ref 撤单、合约品种兜底、软止损 tick 取整 —— 4 项全部通过。
- `execution_framework/test_position_lifecycle.py`：新增 `test_partial_exit_quantity_is_never_resurrected`、`test_persistence_survives_process_restart`、`test_restore_of_open_position_keeps_cap_clock` —— 全部通过。
- `execution_framework/test_intent_ledger.py`：新增 `test_state_transition_table`、`test_fencing_token_blocks_stale_leader`、`test_fencing_column_migration_on_old_database` —— 全部通过。
- `execution_framework/test_session_timezone.py`（新增）：指数/国债时段夏冬令时跟随美东、24h 品种、旧 UTC 字段兼容、跨午夜窗口、朴素时间戳拒绝 —— 6 项全部通过。
- `execution_framework/test_journal_net_r.py`（新增）：期货多空净 R（乘数+双边费用）、现货退化、旧库迁移、stats 净口径汇总、非法乘数拒绝 —— 6 项全部通过。
- `execution_framework/test_adaptive_poll.py`（新增）：空闲降低频、事件窗口/在途订单/未平仓持仓（OPEN/EXIT_SUBMITTED/EXIT_PARTIAL）/活跃软止损切高频 —— 5 项全部通过（runner 依赖包外模块，经 AST 抽取真实函数本体测试）。
- `execution_framework/test_rules_coherence.py`（新增）：CL 已接线、每个品种 asset_class 都有硬封顶、参数健全性、五模型产品族齐全 —— 4 项全部通过。
- `execution_framework/test_negative_control.py`（新增）：构造磁带驱动真实引擎点火、延续磁带正 diff/反转磁带负 diff、无突破跳过、止损优先于封顶、置换检验区分信号与噪声、全档案 run() 端到端 —— 7 项全部通过。
- `eventalpha_core/test_microstructure.py`：新增 `test_hard_cap_delegated_to_lifecycle_monitor` —— 需完整仓库运行；已用桩模块独立验证逻辑。
- 管线 fencing 接线冒烟测试（桩模块替代包外依赖）：`configure_lease_guard` 启用/失效路径、`.lifecycle.db` 默认落盘 —— 通过。

## 本包之外、运行完整测试所需的基础模块（不在 zip 内）

- eventalpha_core: `schema.py`、`advanced/microstructure.py`、`advanced/measured_timing.py`、`v2`
- execution_framework: `enabled_symbols`、`runtime_guardian`、`ibkr_contract_resolver`、`ibkr_session`、`hard_stop`、`correct_position_sizer`、`v2_telemetry`、`microstructure_shadow`、`timeseries_shadow`、`news_shadow`、`economic_calendar`、`rss_news_feed`、`eia_feed`

建议：以 git 仓库 base commit 哈希 + 本哈希清单共同锚定可复现基线。

## 复核验证结果（2026-08-27）

- test_review_fixes / test_position_lifecycle / test_intent_ledger / test_event_data_archive / test_session_timezone / test_journal_net_r / test_adaptive_poll / test_rules_coherence / test_negative_control：全部通过（独立运行；test_intent_ledger 连跑 5 次验证并发初始化加固后无偶发锁定失败）。
- test_fakeout_live / test_crypto_spot / test_account_risk_snapshot / test_journal_guardian / test_pipeline_dryrun / test_microstructure：依赖上述基础模块，需并入主仓库后运行。
- 全部 29 个文件 py_compile 通过。

## 文件 SHA-256 清单

79d817f8d416d2f18181ed6bc5c77015944cb872b57f78b7be13e45a5513a875  ./SECOND_STAGE_IMPLEMENTATION_NOTES_20260827.md
0991ea18f0b8ae98cb161a410e7c851918a3c0b1fc8ae615f732a83f6a1b0172  ./eventalpha_core/advanced/escape_engine.py
097b41526bc68660fa1c8eb947c6a1045c7e5def2d8da1389a066bd3bf850ff3  ./eventalpha_core/test_microstructure.py
ddd98ebc2637585c2633f1446e2c6e6486c6346d6ecdd86ba86556b93db59eaa  ./eventalpha_intraday_study/execution_backtest.py
5a23f4af1fcbad366daa691146f81c39da2176857d74c4317d0161b0a87228ec  ./eventalpha_intraday_study/test_causal_replay.py
386947aa3572813d24d39ac1789d9ae311986ca2fd12c78e6615d7b7b28f2f76  ./eventalpha_intraday_study/v2_replay.py
cdf573bdd4c3f9d21d9f4f929555bb558216bedff991d831352247e36cab7760  ./execution_framework/depth_collector.py
08330138b8f710f57c454259f501026e3dbec09b211a4447f68b7b173f9deb94  ./execution_framework/event_data_archive.py
74512d564de86562382a344c201cbfb125f38e15287e96521fb400477b965373  ./execution_framework/event_right_side_engine.py
e9997c0fa5ab4992774529f7d5f7b766d7b1ce156e8005b96138201c05a0ca32  ./execution_framework/ibkr_order_manager.py
c32db7c8b47024a23348db8f5174b4f171210b2c2c8ea580dc403370bf8a3ea9  ./execution_framework/intent_ledger.py
e3dc24f5535898f390431a90b57145e6828b2cab859f1c0f6ee530d3c8df0a79  ./execution_framework/negative_control.py
15f689854307d8cbe9c3565619ea0aa60a59909a309e859174b908a7b8d05ae1  ./execution_framework/position_lifecycle.py
ab60f752b4b88cd1b90752b57fb7e3c812685eb7c073eea8db602cdf154275f9  ./execution_framework/right_side_pipeline.py
d382745b0c9f38ddc7a2976966941e2b9d4269b0ad39c712831672a90321921a  ./execution_framework/run_tws_continuous.py
a9b996c5cc16c498d6c1156b11394cd422119d98a0684e6ce66acc843c551b6f  ./execution_framework/test_account_risk_snapshot.py
787ec28a48a49d4c3e4cbbc66d2d0709f286977483362393edfe8fd88a89df02  ./execution_framework/test_adaptive_poll.py
941838a7e1ab921181d6970d6c8f83d287234a1806d5262400ce750e14017be3  ./execution_framework/test_crypto_spot.py
d93d15e7b9741cf0ca23c858f85956b5aa4af2ad7bdf6cfeac4432bc87add15c  ./execution_framework/test_event_data_archive.py
764df0e51d269307c351174f604d8df29c06c0c8438b8f4635e8bc4e39876e7c  ./execution_framework/test_fakeout_live.py
5de6b1d1f92669ea668de4ba53803cb8a6c3e1b3beeeaaf202a13f8deac9e325  ./execution_framework/test_intent_ledger.py
999a923fa931e9fa26397bebae84553042b98dbca2cd60cfad0d4b8d2608e56b  ./execution_framework/test_journal_guardian.py
2e3f75b9331ec859b195c82317059457675741bf65ee89b60ad828519338d390  ./execution_framework/test_journal_net_r.py
df65431e25bc58be7ad6a028848231f3dcb7e2f153879639f730d7200b46a73e  ./execution_framework/test_negative_control.py
234d7e3355ab82f3b7a04d712c767918bd8d80e3f064927469b055ffd4d91e52  ./execution_framework/test_pipeline_dryrun.py
881ef5cf1c374e211d6381b2c9f372a4ba7d966bfe39caa8cef06b35cb2bb231  ./execution_framework/test_position_lifecycle.py
a28304e3df21423965785dc6fb47a101c54a80a7be1c347ff1b09037c7af2dda  ./execution_framework/test_review_fixes.py
3c613c4867363ebfc15d16a8cbf807e4b18b81a33286ace1bf80709b5c0d3363  ./execution_framework/test_rules_coherence.py
342571037a4eae715094bb7ca416f9155bed7c192478538cb1a8d5f20d716724  ./execution_framework/test_session_timezone.py
c0110ea3eafb3545b38a56c7324cf0681d7e97ecb09cb3bf99a0b556afe8d4ca  ./execution_framework/trade_journal.py

## 主仓库并入验证（2026-08-28）

- 仓库：github.com/tongyin2020/insightbridge-latest-financial-models，基线提交 `a10b97e`，并入分支 `merge/stage2-review-fixes`（本地，未推送）。
- 差异核对：补丁全部文件相对仓库为严格更新/超集（仓库同名文件最后提交 2026-07-05，补丁无反向覆盖）。
- 依赖主仓库的 6 个套件全部通过：test_pipeline_dryrun / test_journal_guardian / test_account_risk_snapshot / test_fakeout_live / test_crypto_spot / eventalpha_core/test_microstructure；连同补丁内 9 个套件共 15 个全绿。
- CL 确认：`enabled_symbols.py` 原无 CL（五模型确实只有四个接线）；已将 CL 登记入 `DISABLED_SYMBOLS` 并加备注——规则已就绪，确认模拟账户 NYMEX 权限后移入 `ENABLED_SYMBOLS` 即可（未擅自启用，避免对无权限品种发单）。
- FOMC 确认：`economic_calendar.py` 与 `seed_calendar_2026_07.py` 中 FOMC 为单一事件对象（声明 14:00 ET），记者会 14:30 ET 未拆分。拆分与否是策略决策（拆分将消耗 2 个年度事件预算、产生两个冷静期窗口），未擅自改动；建议维持单事件并把记者会窗口按持仓管理期处理，或在明确决定后再改。
