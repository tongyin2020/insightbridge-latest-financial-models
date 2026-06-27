from __future__ import annotations

import json
import subprocess
from pathlib import Path


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main() -> None:
    files = [
        BASE / "eventalpha_core" / "eventalpha_brain.py",
        BASE / "eventalpha_core" / "event_memory.py",
        BASE / "eventalpha_core" / "learning_engine.py",
        BASE / "01_Crypto_BTC_ETH_SOL" / "eventalpha_adapter.py",
        BASE / "03_FX_AUD_NZD_EUR_GBP" / "backend" / "eventalpha_adapter.py",
        BASE / "04_WTI_Oil_Futures" / "backend" / "eventalpha_adapter.py",
        BASE / "05_Bond_Treasury" / "backend" / "eventalpha_adapter.py",
        BASE / "02_StockIndex_IBKR_ES_NQ" / "eventalpha_adapter.py",
        BASE / "run_eventalpha_paper.py",
        BASE / "run_eventalpha_historical_replay.py",
    ]
    for f in files:
        run(["python3", "-m", "py_compile", str(f)])

    out = run([
        "python3",
        str(BASE / "run_eventalpha_paper.py"),
        "--event-type",
        "opec",
        "--title",
        "Verification OPEC event",
        "--top-n",
        "5",
    ])
    print(out)
    replay_out = run([
        "python3",
        str(BASE / "run_eventalpha_historical_replay.py"),
    ])
    print(replay_out)
    print("\nFull stack verification: OK")


if __name__ == "__main__":
    main()
