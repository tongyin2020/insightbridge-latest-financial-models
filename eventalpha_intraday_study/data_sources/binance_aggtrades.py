"""Download and parse real Binance spot aggTrades (tick-level) daily archives.

Source: https://data.binance.vision  (official Binance public data, free, no key).
This is genuine exchange-matched trade data, not broker/CFD quotes.

Each daily archive is a zip containing one headerless CSV:
    agg_trade_id, price, quantity, first_trade_id, last_trade_id,
    transact_time, is_buyer_maker, is_best_match

`is_buyer_maker == False` means the aggressor was a market BUY (lifted the ask),
so signed aggressive volume = +qty; when True it is a market SELL = -qty.

Timestamps: milliseconds through 2024, microseconds from ~2025-01. We detect the
unit by magnitude so both parse correctly.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from ..config import binance_dir

BASE = "https://data.binance.vision/data/spot/daily/aggTrades"
COLUMNS = [
    "agg_trade_id", "price", "quantity", "first_trade_id",
    "last_trade_id", "transact_time", "is_buyer_maker", "is_best_match",
]


def _daily_url(symbol: str, d: date) -> str:
    return f"{BASE}/{symbol}/{symbol}-aggTrades-{d.isoformat()}.zip"


def download_day(symbol: str, d: date, force: bool = False) -> Path | None:
    """Download one day's zip to the cache. Returns local path or None if 404."""
    out = binance_dir() / f"{symbol}-aggTrades-{d.isoformat()}.zip"
    if out.exists() and not force and out.stat().st_size > 0:
        return out
    url = _daily_url(symbol, d)
    resp = requests.get(url, timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


def _to_datetime(series: pd.Series) -> pd.Series:
    # ms vs us: ms epoch for 2024 ~ 1.7e12; us epoch ~ 1.7e15.
    unit = "us" if series.iloc[0] > 1e14 else "ms"
    return pd.to_datetime(series, unit=unit, utc=True)


def load_day(symbol: str, d: date) -> pd.DataFrame | None:
    """Return tidy tick DataFrame: Time(UTC), Price, Quantity, SignedVol."""
    path = download_day(symbol, d)
    if path is None:
        return None
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(name) as f:
            df = pd.read_csv(f, header=None, names=COLUMNS)
    df["Time"] = _to_datetime(df["transact_time"])
    df["Price"] = df["price"].astype(float)
    df["Quantity"] = df["quantity"].astype(float)
    maker = df["is_buyer_maker"].astype(str).str.lower().isin(["true", "1"])
    df["SignedVol"] = df["Quantity"].where(~maker, -df["Quantity"])
    return df[["Time", "Price", "Quantity", "SignedVol"]].sort_values("Time").reset_index(drop=True)


def load_window(symbol: str, day: date, pre_days: int = 0, post_days: int = 0) -> pd.DataFrame | None:
    """Load [day-pre_days, day+post_days] concatenated (for events near midnight)."""
    frames = []
    for off in range(-pre_days, post_days + 1):
        part = load_day(symbol, day + timedelta(days=off))
        if part is not None:
            frames.append(part)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True).sort_values("Time").reset_index(drop=True)


if __name__ == "__main__":
    df = load_day("BTCUSDT", date(2024, 5, 15))
    assert df is not None
    print(df.head())
    print(f"rows={len(df):,}  span={df['Time'].iloc[0]} .. {df['Time'].iloc[-1]}")
