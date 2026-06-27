"""
WTI v1 — 核心配置文件
所有参数集中在此，不得分散硬编码到各模块。
修改参数后必须重启系统生效。
"""

from dataclasses import dataclass, field
from typing import Optional
import os


# ─────────────────────────────────────────────
# 交易品种
# ─────────────────────────────────────────────
SYMBOL = "CL"           # WTI原油期货 (Tradovate: CL | IBKR: CL)
EXCHANGE = "NYMEX"
CURRENCY = "USD"
CONTRACT_SIZE = 1000    # 每手 1000 桶


# ─────────────────────────────────────────────
# 风控参数（硬性限制，不可被信号覆盖）
# ─────────────────────────────────────────────
@dataclass
class RiskConfig:
    # 单笔最大风险（账户净值百分比）
    max_risk_per_trade_pct: float = 0.005       # 0.5%
    # 每日最大亏损（账户净值百分比）
    max_daily_loss_pct: float = 0.015           # 1.5%
    # 连续亏损笔数 → 自动停手
    max_consecutive_losses: int = 3
    # 最大点差（超过则拒绝下单）
    max_spread_ticks: float = 6.0
    # 最大可接受滑点（ticks）
    max_slippage_ticks: float = 4.0
    # 数据中断容忍时间（秒）
    data_gap_timeout_sec: int = 30
    # 账户净值（需运行时从平台读取更新）
    account_equity: float = 50000.0


# ─────────────────────────────────────────────
# 持仓与退出参数
# ─────────────────────────────────────────────
@dataclass
class HoldingConfig:
    # 常规目标持仓时间（分钟）
    target_hold_min: int = 25
    # 强趋势可延长至（分钟）
    max_hold_min: int = 45
    # 若N分钟无延续则提前退出
    early_exit_no_momentum_min: int = 10
    # 反向强冲击时立即保护（分钟内）
    reverse_shock_exit_min: int = 5
    # 分批退出比例（首批）
    partial_exit_ratio: float = 0.5


# ─────────────────────────────────────────────
# 信号确认参数（我的改进：基于价格行为而非固定时间）
# ─────────────────────────────────────────────
@dataclass
class ConfirmationConfig:
    # 事件后观察窗口（秒）—— 最短等待
    min_wait_sec: int = 20
    # 最长等待（超过则跳过本次事件）
    max_wait_sec: int = 90
    # 必须突破事件后初始振幅的比例才算有效突破
    breakout_pct_of_range: float = 0.60
    # EMA快线周期
    ema_fast: int = 20
    # EMA慢线周期
    ema_slow: int = 50
    # ADX确认趋势强度阈值
    adx_threshold: float = 22.0
    # VWAP偏离容忍（ATR倍数）
    vwap_atr_max_deviation: float = 1.5
    # 尖刺过滤：单根K线振幅不得超过N倍ATR
    spike_filter_atr_mult: float = 3.0
    # 最低成交量确认（相对20周期均量倍数）
    min_volume_ratio: float = 1.2


# ─────────────────────────────────────────────
# 环境识别参数（量化标准，我的改进）
# ─────────────────────────────────────────────
@dataclass
class RegimeConfig:
    # 波动率高于N倍历史均值 → event/trend模式
    vol_spike_multiplier: float = 1.8
    # ATR（14）相对基准的倍数
    atr_baseline_periods: int = 60   # 用60根K线算基准ATR
    # 进入blocked状态的点差阈值（tick）
    blocked_spread_ticks: float = 10.0
    # 进入blocked状态的波动率阈值（超过则太乱）
    blocked_vol_multiplier: float = 4.0


# ─────────────────────────────────────────────
# 事件分类（A/B/C）
# ─────────────────────────────────────────────
EVENT_PRIORITY = {
    # A类：最高优先级，直接触发event模式
    "A": [
        "EIA_crude_inventory",
        "OPEC_meeting_decision",
        "OPEC_production_change",
        "middle_east_escalation",
        "hormuz_strait_risk",
        "major_supply_disruption",
    ],
    # B类：中高优先级，需额外确认
    "B": [
        "API_crude_inventory",
        "fed_rate_decision",
        "fed_chair_speech",
        "us_cpi",
        "us_ppi",
        "us_nonfarm_payroll",
        "china_gdp",
        "china_pmi",
    ],
    # C类：低优先级，通常跳过
    "C": [
        "analyst_comment",
        "repeat_news",
        "minor_geopolitical",
    ],
}

# 各类事件确认窗口（秒）
EVENT_CONFIRM_WINDOW = {
    "A": (20, 45),    # (min_sec, max_sec)
    "B": (30, 60),
    "C": (0, 0),      # 不进入event模式
}


# ─────────────────────────────────────────────
# 平台配置（v1先用paper broker）
# ─────────────────────────────────────────────
@dataclass
class BrokerConfig:
    mode: str = "paper"          # "paper" | "tradovate" | "ibkr"
    # Tradovate
    tradovate_api_url: str = "https://api.tradovate.com/v1"
    tradovate_ws_url: str = "wss://md.tradovate.com/v1/websocket"
    tradovate_username: str = os.getenv("TRADOVATE_USER", "")
    tradovate_password: str = os.getenv("TRADOVATE_PASS", "")
    # IBKR
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1


# ─────────────────────────────────────────────
# 日志配置
# ─────────────────────────────────────────────
LOG_DIR = "logs"
LOG_LEVEL = "INFO"
LOG_ROTATION = "1 day"
LOG_RETENTION = "30 days"


# ─────────────────────────────────────────────
# 全局配置实例（直接 import 使用）
# ─────────────────────────────────────────────
RISK = RiskConfig()
HOLDING = HoldingConfig()
CONFIRM = ConfirmationConfig()
REGIME = RegimeConfig()
BROKER = BrokerConfig()
