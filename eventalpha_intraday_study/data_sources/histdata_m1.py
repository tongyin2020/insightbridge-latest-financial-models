"""Download and parse HistData.com 1-minute bar quotes (FX + commodities).

Free, no account. Covers the two assets Dukascopy's free feed is unreachable for:
  FX:  EURUSD, USDJPY, ...            (interbank-derived)
  Oil: WTIUSD (WTI crude), BCOUSD (Brent)   (CFD, adequate for event timing)

Resolution is 1 minute (not tick), so reaction latency / washout are measured to
~60s granularity; trend lifetime / retracement (the retail-tradeable timescales)
are captured cleanly.

Download mechanism: the per-year page embeds a token `tk` in its HTML. POST that
token to /get.php to receive the whole-year zip (one CSV of M1 bars).

CSV format (headerless, ';'-separated):
    YYYYMMDD HHMMSS;Open;High;Low;Close;Volume
Timestamps are US Eastern Standard Time WITHOUT DST (fixed UTC-5), per HistData's
spec, so we localise as a constant -5h offset and convert to UTC.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

from ..config import histdata_dir

BASE = "https://www.histdata.com"
EST = timezone(timedelta(hours=-5))   # HistData: EST, no DST
_TK_RE = re.compile(r'id="tk"[^>]*value="([a-f0-9]{16,})"', re.I)


def _year_page(pair: str, year: int) -> str:
    return f"{BASE}/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{pair.lower()}/{year}"


def download_year(pair: str, year: int, force: bool = False) -> Path | None:
    """Download one pair-year M1 zip. Returns local path, or None if unavailable."""
    out = histdata_dir() / f"HISTDATA_{pair.upper()}_M1_{year}.zip"
    if out.exists() and not force and out.stat().st_size > 1000:
        return out

    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0"})
    ref = _year_page(pair, year)
    page = sess.get(ref, timeout=30)
    page.raise_for_status()
    m = _TK_RE.search(page.text)
    if not m:
        return None
    tk = m.group(1)

    resp = sess.post(
        f"{BASE}/get.php",
        data={"tk": tk, "date": str(year), "datemonth": str(year),
              "platform": "ASCII", "timeframe": "M1", "fxpair": pair.upper()},
        headers={"Referer": ref, "X-Requested-With": "XMLHttpRequest"},
        timeout=120,
    )
    resp.raise_for_status()
    if len(resp.content) < 1000 or resp.content[:2] != b"PK":
        return None
    out.write_bytes(resp.content)
    return out


def load_year(pair: str, year: int) -> pd.DataFrame | None:
    """Return tidy 1-min bars: Time(UTC), Open, High, Low, Close."""
    path = download_year(pair, year)
    if path is None:
        return None
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(name) as f:
            df = pd.read_csv(f, sep=";", header=None,
                            names=["ts", "Open", "High", "Low", "Close", "Volume"])
    t_local = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S").dt.tz_localize(EST)
    df["Time"] = t_local.dt.tz_convert(timezone.utc)
    for c in ("Open", "High", "Low", "Close"):
        df[c] = df[c].astype(float)
    return df[["Time", "Open", "High", "Low", "Close"]].sort_values("Time").reset_index(drop=True)


def load_years(pair: str, years: list[int]) -> pd.DataFrame | None:
    frames = [d for y in years if (d := load_year(pair, y)) is not None]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True).sort_values("Time").reset_index(drop=True)


def to_pricevol(bars: pd.DataFrame) -> pd.DataFrame:
    """Adapt OHLC bars to the (Time, Price, SignedVol) frame the study consumes.

    Price = Close; SignedVol = 0 (HistData has no volume for these instruments)."""
    out = pd.DataFrame({"Time": bars["Time"], "Price": bars["Close"], "SignedVol": 0.0})
    return out


if __name__ == "__main__":
    for pair in ("EURUSD", "USDJPY", "WTIUSD", "BCOUSD"):
        d = load_year(pair, 2024)
        if d is None:
            print(f"{pair} 2024: UNAVAILABLE")
        else:
            print(f"{pair} 2024: rows={len(d):,} {d['Time'].iloc[0]} .. {d['Time'].iloc[-1]}")
