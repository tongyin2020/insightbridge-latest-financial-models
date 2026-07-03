"""Load the per-instrument tick CSVs exported by EventTickExportStrategy.java.

CSV columns: timestamp_ms,bid,ask,bidVol,askVol  (JForex authenticated history).

Produces the (Time, Price, SignedVol) frame the event study consumes:
  Price    = mid = (bid + ask) / 2
  SignedVol = 0   (Dukascopy ticks carry bid/ask sizes, not signed trade flow)
"""
from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pandas as pd

from ..config import data_dir

# logical instrument -> exported file token (matches Java: strip '/' and '.')
DEFAULT_TICK_DIR = "jforex_ticks"


def _tick_path(logical: str, tick_dir: Path) -> Path:
    token = logical.replace("/", "").replace(".", "")
    return tick_dir / f"ticks_{token}.csv"


def load_ticks(logical: str, tick_dir: Path | None = None) -> pd.DataFrame | None:
    tick_dir = tick_dir or (data_dir() / DEFAULT_TICK_DIR)
    path = _tick_path(logical, tick_dir)
    if not path.exists() or path.stat().st_size < 50:
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    df["Time"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    df["Price"] = (df["bid"].astype(float) + df["ask"].astype(float)) / 2.0
    df["SignedVol"] = 0.0
    return (df[["Time", "Price", "SignedVol"]]
            .dropna(subset=["Price"])
            .drop_duplicates(subset=["Time"])
            .sort_values("Time")
            .reset_index(drop=True))


if __name__ == "__main__":
    for logical in ("EUR/USD", "USD/JPY", "LIGHT.CMD/USD"):
        d = load_ticks(logical)
        if d is None:
            print(f"{logical}: no export yet (run EventTickExportStrategy in JForex4)")
        else:
            print(f"{logical}: {len(d):,} ticks {d['Time'].iloc[0]} .. {d['Time'].iloc[-1]}")
