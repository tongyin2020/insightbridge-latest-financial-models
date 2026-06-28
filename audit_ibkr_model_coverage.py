#!/usr/bin/env python3
"""
Audit how the five local financial models are wired to IBKR paper trading.

This is a static code audit only. It does not connect or place orders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")


@dataclass
class ModelCoverage:
    model: str
    status: str
    execution_path: str
    evidence: list[str]
    risk_note: str


def exists(rel: str) -> bool:
    return (BASE / rel).exists()


def main() -> int:
    rows = [
        ModelCoverage(
            model="Crypto (BTC/ETH/SOL)",
            status="PARTIAL",
            execution_path="Unified IBKR connector exists, but this model does not have its own dedicated IBKR adapter in the crypto folder.",
            evidence=[
                str(BASE / "02_StockIndex_IBKR_ES_NQ" / "live_trader.py"),
                str(BASE / "02_StockIndex_IBKR_ES_NQ" / "ibkr_connector.py"),
                str(BASE / "01_Crypto_BTC_ETH_SOL" / "eventalpha_adapter.py"),
            ],
            risk_note="Tradable through the unified connector, but not yet cleanly isolated as a standalone crypto-to-IBKR execution service.",
        ),
        ModelCoverage(
            model="Stock Index",
            status="PARTIAL",
            execution_path="Shared stock-index tool contains an IB executor, but it is still labeled as a placeholder/stub.",
            evidence=[
                str(BASE / "shared_stockindex_tool_crewai.py"),
                str(BASE / "02_StockIndex_IBKR_ES_NQ" / "eventalpha_adapter.py"),
            ],
            risk_note="This is the weakest link for direct live/paper execution. Index logic exists, but the dedicated execution layer still needs finishing.",
        ),
        ModelCoverage(
            model="FX (AUD/NZD/EUR/GBP)",
            status="READY",
            execution_path="Dedicated IB TWS/Gateway adapter exists and is the cleanest production-style IBKR path in the project.",
            evidence=[
                str(BASE / "03_FX_AUD_NZD_EUR_GBP" / "fx_trading_system" / "adapters" / "ib_tws" / "ib_adapter.py"),
                str(BASE / "03_FX_AUD_NZD_EUR_GBP" / "fx_trading_system" / "adapters" / "ib_tws" / "requirements.txt"),
                str(BASE / "03_FX_AUD_NZD_EUR_GBP" / "fx_trading_system" / "scripts" / "start_ib_adapter.sh"),
            ],
            risk_note="This is the best candidate if you want to validate one model against IBKR first.",
        ),
        ModelCoverage(
            model="WTI Oil Futures",
            status="PARTIAL",
            execution_path="Unified IBKR connector supports CL futures, but the oil folder itself does not expose a dedicated IBKR execution service.",
            evidence=[
                str(BASE / "02_StockIndex_IBKR_ES_NQ" / "ibkr_connector.py"),
                str(BASE / "02_StockIndex_IBKR_ES_NQ" / "live_trader.py"),
                str(BASE / "04_WTI_Oil_Futures" / "backend" / "eventalpha_adapter.py"),
            ],
            risk_note="Operationally usable through the shared connector, but architecture is still mixed.",
        ),
        ModelCoverage(
            model="Bond / Rates",
            status="PARTIAL",
            execution_path="Unified IBKR connector supports ZN futures, but the bond folder itself remains centered on internal paper-trading services.",
            evidence=[
                str(BASE / "02_StockIndex_IBKR_ES_NQ" / "ibkr_connector.py"),
                str(BASE / "05_Bond_Treasury" / "backend" / "eventalpha_adapter.py"),
                str(BASE / "05_Bond_Treasury" / "backend" / "services" / "paper_trading.py"),
            ],
            risk_note="Usable through the shared connector, but not yet cleanly separated into a bond-specific IBKR execution layer.",
        ),
    ]

    summary = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "base": str(BASE),
        "models": [asdict(r) for r in rows],
        "conclusion": {
            "best_current_ibkr_path": "FX adapter + unified connector",
            "models_with_clean_dedicated_ibkr_path": ["FX"],
            "models_supported_via_unified_ibkr_connector": ["Crypto", "FX", "WTI Oil", "Bond/Rates"],
            "model_needing_more_work_for_clean_ibkr_execution": ["Stock Index"],
        },
    }

    print("IBKR Model Coverage Audit")
    print("=" * 60)
    print(f"base: {BASE}")
    print("-" * 60)
    for row in rows:
        print(f"[{row.model}]")
        print(f"status: {row.status}")
        print(f"path: {row.execution_path}")
        print(f"risk: {row.risk_note}")
        print("evidence:")
        for item in row.evidence:
            print(f"  - {item}")
        print("-" * 60)

    print(json.dumps(summary["conclusion"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
