"""Shared configuration for the intraday event study.

Everything is path-independent so it runs on the Linux research VM or on the
Mac. Override the data directory with the EVENTALPHA_DATA_DIR env var.
"""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    root = os.environ.get("EVENTALPHA_DATA_DIR", str(Path.home() / "eventalpha_data"))
    p = Path(root).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def binance_dir() -> Path:
    p = data_dir() / "binance"
    p.mkdir(parents=True, exist_ok=True)
    return p


def dukascopy_dir() -> Path:
    p = data_dir() / "dukascopy"
    p.mkdir(parents=True, exist_ok=True)
    return p


def histdata_dir() -> Path:
    p = data_dir() / "histdata"
    p.mkdir(parents=True, exist_ok=True)
    return p


def reports_dir() -> Path:
    p = data_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p
