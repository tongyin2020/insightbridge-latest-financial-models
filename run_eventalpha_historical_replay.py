"""
Starter historical event replay harness for EventAlpha 2.1.

This is still paper-only. It exists to validate that:
1. event -> ranking -> decision chain runs
2. replay outcomes feed back into EventMemoryDB
3. regime / exit / learning modules are truly connected
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from eventalpha_core import AssetClass, EventMemoryDB, EventType, LearningEngine
from eventalpha_core.advanced.post_event_learning import TradeReplay


SCENARIOS = [
    {"event_type": "cpi", "asset": "fx", "symbol": "AUD/USD", "direction": "short", "final_r": 1.4, "mfe_r": 2.1, "mae_r": -0.3, "wait_used": 90, "best_wait": 150, "exit_reason": "target_hit", "entry_conf": 0.81, "exit_conf": 0.63, "false_breakout": False},
    {"event_type": "cpi", "asset": "rates", "symbol": "ZN", "direction": "short", "final_r": 1.1, "mfe_r": 1.8, "mae_r": -0.4, "wait_used": 75, "best_wait": 120, "exit_reason": "trailing_exit", "entry_conf": 0.79, "exit_conf": 0.58, "false_breakout": False},
    {"event_type": "cpi", "asset": "index", "symbol": "ES_PROXY", "direction": "short", "final_r": -0.9, "mfe_r": 0.3, "mae_r": -1.1, "wait_used": 30, "best_wait": 140, "exit_reason": "stop_loss", "entry_conf": 0.74, "exit_conf": 0.40, "false_breakout": True},
    {"event_type": "fomc", "asset": "fx", "symbol": "AUD/USD", "direction": "short", "final_r": 0.8, "mfe_r": 1.5, "mae_r": -0.5, "wait_used": 120, "best_wait": 180, "exit_reason": "time_exit", "entry_conf": 0.77, "exit_conf": 0.54, "false_breakout": False},
    {"event_type": "fomc", "asset": "rates", "symbol": "ZN", "direction": "long", "final_r": 1.6, "mfe_r": 2.3, "mae_r": -0.2, "wait_used": 180, "best_wait": 210, "exit_reason": "target_hit", "entry_conf": 0.84, "exit_conf": 0.66, "false_breakout": False},
    {"event_type": "fomc", "asset": "crypto", "symbol": "BTC", "direction": "long", "final_r": 0.4, "mfe_r": 1.4, "mae_r": -0.6, "wait_used": 45, "best_wait": 120, "exit_reason": "profit_giveback", "entry_conf": 0.76, "exit_conf": 0.49, "false_breakout": True},
    {"event_type": "nfp", "asset": "fx", "symbol": "AUD/USD", "direction": "long", "final_r": 1.0, "mfe_r": 1.7, "mae_r": -0.4, "wait_used": 60, "best_wait": 95, "exit_reason": "trailing_exit", "entry_conf": 0.75, "exit_conf": 0.59, "false_breakout": False},
    {"event_type": "nfp", "asset": "index", "symbol": "ES_PROXY", "direction": "long", "final_r": 1.2, "mfe_r": 1.9, "mae_r": -0.3, "wait_used": 70, "best_wait": 110, "exit_reason": "target_hit", "entry_conf": 0.80, "exit_conf": 0.61, "false_breakout": False},
    {"event_type": "opec", "asset": "oil", "symbol": "WTI", "direction": "long", "final_r": 1.9, "mfe_r": 2.6, "mae_r": -0.3, "wait_used": 240, "best_wait": 260, "exit_reason": "trend_follow", "entry_conf": 0.87, "exit_conf": 0.69, "false_breakout": False},
    {"event_type": "opec", "asset": "index", "symbol": "ES_PROXY", "direction": "short", "final_r": 0.5, "mfe_r": 1.1, "mae_r": -0.4, "wait_used": 120, "best_wait": 180, "exit_reason": "time_exit", "entry_conf": 0.70, "exit_conf": 0.47, "false_breakout": False},
    {"event_type": "eia_inventory", "asset": "oil", "symbol": "WTI", "direction": "short", "final_r": -0.8, "mfe_r": 0.2, "mae_r": -1.0, "wait_used": 15, "best_wait": 90, "exit_reason": "stop_loss", "entry_conf": 0.71, "exit_conf": 0.36, "false_breakout": True},
    {"event_type": "eia_inventory", "asset": "rates", "symbol": "ZN", "direction": "flat", "final_r": 0.1, "mfe_r": 0.3, "mae_r": -0.1, "wait_used": 40, "best_wait": 40, "exit_reason": "no_trade", "entry_conf": 0.55, "exit_conf": 0.55, "false_breakout": False},
    {"event_type": "geopolitical", "asset": "oil", "symbol": "WTI", "direction": "long", "final_r": 2.2, "mfe_r": 3.0, "mae_r": -0.5, "wait_used": 300, "best_wait": 360, "exit_reason": "event_extension", "entry_conf": 0.89, "exit_conf": 0.73, "false_breakout": False},
    {"event_type": "geopolitical", "asset": "crypto", "symbol": "BTC", "direction": "short", "final_r": -0.6, "mfe_r": 0.5, "mae_r": -0.9, "wait_used": 30, "best_wait": 150, "exit_reason": "thesis_break", "entry_conf": 0.68, "exit_conf": 0.33, "false_breakout": True},
    {"event_type": "liquidity_shock", "asset": "rates", "symbol": "ZN", "direction": "long", "final_r": 1.8, "mfe_r": 2.4, "mae_r": -0.3, "wait_used": 210, "best_wait": 240, "exit_reason": "flight_to_quality", "entry_conf": 0.86, "exit_conf": 0.68, "false_breakout": False},
]


def main() -> None:
    memory_path = BASE / "reports" / "eventalpha_memory.sqlite"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    learning = LearningEngine(EventMemoryDB(str(memory_path)))
    results = []
    for item in SCENARIOS:
        replay = TradeReplay(
            event_type=item["event_type"],
            asset=item["asset"],
            symbol=item["symbol"],
            predicted_direction=item["direction"],
            final_outcome_r=item["final_r"],
            max_favorable_r=item["mfe_r"],
            max_adverse_r=item["mae_r"],
            wait_seconds_used=item["wait_used"],
            best_wait_seconds_hindsight=item["best_wait"],
            exit_reason=item["exit_reason"],
            confidence_at_entry=item["entry_conf"],
            confidence_at_exit=item["exit_conf"],
            false_breakout=item["false_breakout"],
        )
        results.append(learning.apply_replay_learning(replay))

    summary = {}
    for row in results:
        key = f'{row["event_type"]}:{row["asset"]}'
        summary[key] = summary.get(key, 0) + 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(SCENARIOS),
        "coverage": summary,
        "learning_updates": results,
    }
    out_dir = BASE / "reports" / "eventalpha_replays"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"eventalpha_historical_replay_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
