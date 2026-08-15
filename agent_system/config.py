from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AgentConfig:
    base_dir: Path
    observe_only: bool = True
    execution_enabled: bool = False
    # init=False fields must be set in __post_init__
    trace_dir: Path = field(init=False, repr=False)
    log_window_minutes: float = 60.0
    news_lookback_minutes: float = 30.0
    gatekeeper_weights: dict[str, float] = field(default_factory=lambda: {
        "news": 0.35,
        "volatility": 0.35,
        "microstructure": 0.15,
        "pipeline_health": 0.15,
    })
    crisis_threshold: float = 0.55
    macro_alert_keywords: list[str] = field(default_factory=lambda: [
        "war", "iran", "israel", "gaza", "ukraine", "russia", "china",
        "boj", "fed", "intervention", "sanctions", "missile", "invasion",
        "conflict", "strike", "terror", "embargo", "tariff", "default",
        "crisis", "recession", "debt ceiling", "government shutdown",
        "oil shock", "currency war",
    ])
    typical_move_frac: dict[str, float] = field(default_factory=lambda: {
        "BTC": 0.025, "ETH": 0.030, "SOL": 0.040,
        "AUDUSD": 0.008, "NZDUSD": 0.009,
        "ZN": 0.006, "ZT": 0.004,
        "CL": 0.018, "MES": 0.010, "MNQ": 0.012,
    })
    bot_symbols: dict[str, list[str]] = field(default_factory=lambda: {
        "crypto": ["BTC", "ETH", "SOL"],
        "fx": ["AUDUSD", "NZDUSD"],
        "bond": ["ZN", "ZT"],
        "oil": ["CL"],
        "index": ["MES", "ES_PROXY"],
    })
    # Phase 1 crisis-reasoning subgraph settings
    use_llm: bool = False
    llm_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    # Consensus / risk thresholds
    critic_min_confidence: float = 0.60
    critic_need_agreement: bool = True
    risk_consec_loss_penalty: int = 2
    risk_max_open_positions: int = 2
    risk_crisis_scale_cap: float = 0.5
    default_position_size: dict[str, float] = field(default_factory=lambda: {
        "crypto": 100.0,    # USD cash qty
        "fx": 10000.0,      # notional
        "bond": 1.0,        # contracts
        "oil": 1.0,
        "index": 1.0,
    })

    def __post_init__(self) -> None:
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.trace_dir = self.base_dir / "reports" / "agent_system"
        self.trace_dir.mkdir(parents=True, exist_ok=True)

    def update(self, values: dict[str, Any]) -> None:
        for k, v in values.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self._ensure_dirs()

    @staticmethod
    def _yaml_path() -> Path:
        return Path(__file__).resolve().parent / "cfg" / "agents.yaml"

    @classmethod
    def from_yaml(cls, base_dir: Path | None = None) -> "AgentConfig":
        if base_dir is None:
            base_dir = Path(os.environ.get("AGENT_BASE", Path(__file__).resolve().parent.parent))
        cfg = cls(base_dir=base_dir)
        yml = cls._yaml_path()
        if yml.exists():
            with yml.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            cfg.update(data)
        return cfg

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "AgentConfig":
        cfg = cls.from_yaml(base_dir=base_dir)
        cfg.observe_only = os.environ.get("AGENT_OBSERVE_ONLY", "1").lower() not in {"0", "false", "off"}
        cfg.execution_enabled = os.environ.get("AGENT_EXECUTION_ENABLED", "0").lower() in {"1", "true", "on"}
        cfg.crisis_threshold = float(os.environ.get("AGENT_CRISIS_THRESHOLD", cfg.crisis_threshold))
        cfg.log_window_minutes = float(os.environ.get("AGENT_LOG_WINDOW_MINUTES", cfg.log_window_minutes))
        cfg.news_lookback_minutes = float(os.environ.get("AGENT_NEWS_LOOKBACK_MINUTES", cfg.news_lookback_minutes))
        cfg.use_llm = os.environ.get("AGENT_USE_LLM", "0").lower() in {"1", "true", "on"}
        cfg.llm_model = os.environ.get("AGENT_LLM_MODEL", cfg.llm_model)
        cfg.llm_base_url = os.environ.get("AGENT_LLM_BASE_URL", cfg.llm_base_url)
        cfg.llm_temperature = float(os.environ.get("AGENT_LLM_TEMPERATURE", cfg.llm_temperature))
        cfg.llm_max_tokens = int(os.environ.get("AGENT_LLM_MAX_TOKENS", cfg.llm_max_tokens))
        if "AGENT_GATEKEEPER_WEIGHTS" in os.environ:
            import json
            cfg.gatekeeper_weights = json.loads(os.environ["AGENT_GATEKEEPER_WEIGHTS"])
        return cfg


DEFAULT_PROMPTS: dict[str, str] = {
    "gatekeeper_reason_monitor": "市场平静：无显著宏观危机信号，Gatekeeper 保持低能耗监控。",
    "gatekeeper_reason_crisis": "检测到宏观危机/波动率异常，Gatekeeper 触发 CRISIS_AWAKEN，准备激活深度研判子图。",
}
