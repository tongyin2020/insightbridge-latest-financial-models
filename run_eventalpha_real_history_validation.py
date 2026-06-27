"""
Real-history bulk validation for the five EventAlpha trading models.

This runner uses:
1. real historical market data (Yahoo Finance)
2. real recurring macro event calendars plus curated shock dates
3. the unified EventAlpha decision brain
4. exact brute-force subset analysis to identify the most robust asset basket

It remains paper-only. No broker action is taken.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")

import sys

if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from eventalpha_core import (  # noqa: E402
    AssetClass,
    Direction,
    EventAlphaBrain,
    EventMemoryDB,
    EventType,
    LearningEngine,
    MacroEvent,
    MarketState,
    load_preferred_assets,
    select_portfolio_candidates,
)


ENTRY_ACTIONS = {"enter_small", "enter_normal", "enter_heavy"}

ASSET_CONFIG = {
    AssetClass.FX: {
        "symbol": "AUD/USD",
        "tickers": ["AUDUSD=X"],
    },
    AssetClass.RATES: {
        "symbol": "ZN",
        "tickers": ["ZN=F", "ZF=F", "^TNX"],
    },
    AssetClass.CRYPTO: {
        "symbol": "BTC",
        "tickers": ["BTC-USD"],
    },
    AssetClass.OIL: {
        "symbol": "WTI",
        "tickers": ["CL=F"],
    },
    AssetClass.INDEX: {
        "symbol": "ES",
        "tickers": ["ES=F", "^GSPC"],
    },
}

EVENT_DEFAULTS = {
    EventType.CPI: dict(surprise_score=0.72, policy_score=0.68, source_confidence=0.82, narrative_bias=-0.10),
    EventType.FOMC: dict(surprise_score=0.66, policy_score=0.82, source_confidence=0.86, narrative_bias=-0.08),
    EventType.NFP: dict(surprise_score=0.62, policy_score=0.54, source_confidence=0.78, narrative_bias=0.02),
    EventType.OPEC: dict(surprise_score=0.64, geopolitical_score=0.22, source_confidence=0.80, narrative_bias=0.18),
    EventType.EIA_INVENTORY: dict(surprise_score=0.58, source_confidence=0.74, narrative_bias=0.12),
    EventType.GEOPOLITICAL: dict(geopolitical_score=0.84, liquidity_score=0.42, source_confidence=0.78, narrative_bias=0.20),
    EventType.LIQUIDITY_SHOCK: dict(liquidity_score=0.88, source_confidence=0.80, narrative_bias=-0.18),
}

EVENT_BIAS = {
    EventType.CPI: {"fx": -1.0, "rates": -1.0, "crypto": -0.5, "oil": -0.2, "index": -1.0},
    EventType.FOMC: {"fx": -1.0, "rates": -1.0, "crypto": -0.6, "oil": -0.2, "index": -1.0},
    EventType.NFP: {"fx": -0.8, "rates": -0.8, "crypto": -0.4, "oil": -0.1, "index": -0.7},
    EventType.OPEC: {"fx": 0.2, "rates": 0.0, "crypto": 0.1, "oil": 1.0, "index": -0.4},
    EventType.EIA_INVENTORY: {"fx": 0.0, "rates": 0.0, "crypto": 0.0, "oil": 0.6, "index": -0.1},
    EventType.GEOPOLITICAL: {"fx": -0.6, "rates": 0.7, "crypto": -0.5, "oil": 1.0, "index": -1.0},
    EventType.LIQUIDITY_SHOCK: {"fx": -0.8, "rates": 1.0, "crypto": -1.0, "oil": -0.5, "index": -1.0},
}


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d


def weekly_wednesdays(start: date, end: date) -> list[date]:
    d = start
    while d.weekday() != 2:
        d += timedelta(days=1)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def build_event_calendar(start_year: int, end_year: int) -> list[dict]:
    fomc_dates = [
        "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
        "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
        "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    ]
    opec_dates = [
        "2022-02-02", "2022-06-02", "2022-10-05", "2022-12-04",
        "2023-04-03", "2023-06-04", "2023-11-30",
        "2024-03-03", "2024-06-02", "2024-12-05",
    ]
    shock_dates = [
        ("2022-02-24", EventType.GEOPOLITICAL, "Russia-Ukraine shock"),
        ("2023-03-13", EventType.LIQUIDITY_SHOCK, "SVB stress spillover"),
        ("2023-10-09", EventType.GEOPOLITICAL, "Middle East escalation"),
        ("2024-04-15", EventType.GEOPOLITICAL, "Regional retaliation shock"),
    ]

    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    rows: list[dict] = []

    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            rows.append(
                {
                    "event_type": EventType.NFP,
                    "event_date": first_friday(year, month),
                    "title": f"NFP {year}-{month:02d}",
                }
            )

    for d in weekly_wednesdays(start, end):
        rows.append(
            {
                "event_type": EventType.EIA_INVENTORY,
                "event_date": d,
                "title": f"EIA Inventory {d.isoformat()}",
            }
        )

    for raw in fomc_dates:
        d = date.fromisoformat(raw)
        if start <= d <= end:
            rows.append({"event_type": EventType.FOMC, "event_date": d, "title": f"FOMC {d.isoformat()}"})

    for raw in opec_dates:
        d = date.fromisoformat(raw)
        if start <= d <= end:
            rows.append({"event_type": EventType.OPEC, "event_date": d, "title": f"OPEC {d.isoformat()}"})

    for raw, event_type, title in shock_dates:
        d = date.fromisoformat(raw)
        if start <= d <= end:
            rows.append({"event_type": event_type, "event_date": d, "title": title})

    rows.sort(key=lambda x: (x["event_date"], x["event_type"].value))
    return rows


def download_history(tickers: list[str], start: str, end: str) -> tuple[str, pd.DataFrame]:
    last_error = None
    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if df is None or df.empty:
                last_error = f"{ticker}: empty"
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            df = df.rename(columns=str.lower).copy()
            required = {"open", "high", "low", "close"}
            if not required.issubset(df.columns):
                last_error = f"{ticker}: missing columns {required - set(df.columns)}"
                continue
            if "volume" not in df.columns:
                df["volume"] = np.nan
            df = df.reset_index().rename(columns={"Date": "date", "date": "date"})
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
            df = df.sort_values("date").reset_index(drop=True)
            return ticker, df
        except Exception as exc:  # pragma: no cover - network/provider dependent
            last_error = f"{ticker}: {exc}"
    raise RuntimeError(f"Unable to download history for {tickers}: {last_error}")


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ret_1"] = out["close"].pct_change()
    out["ret_3"] = out["close"].pct_change(3)
    out["ret_5"] = out["close"].pct_change(5)
    out["ret_20"] = out["close"].pct_change(20)
    out["vol_20"] = out["ret_1"].rolling(20).std()
    out["vol_60"] = out["ret_1"].rolling(60).std()
    tr1 = (out["high"] - out["low"]).abs()
    tr2 = (out["high"] - out["close"].shift(1)).abs()
    tr3 = (out["low"] - out["close"].shift(1)).abs()
    out["true_range"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    out["atr_14"] = out["true_range"].rolling(14).mean()
    delta = out["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))
    out["ema_5"] = out["close"].ewm(span=5, adjust=False).mean()
    out["ema_20"] = out["close"].ewm(span=20, adjust=False).mean()
    if out["volume"].notna().sum() > 10:
        rolling_med = out["volume"].rolling(20).median()
        out["volume_ratio"] = out["volume"] / rolling_med.replace(0, np.nan)
    else:
        out["volume_ratio"] = np.nan
    return out


def previous_index(df: pd.DataFrame, d: date) -> int | None:
    ts = pd.Timestamp(d)
    matches = df.index[df["date"] < ts]
    if len(matches) == 0:
        return None
    return int(matches[-1])


def next_index(df: pd.DataFrame, d: date) -> int | None:
    ts = pd.Timestamp(d)
    matches = df.index[df["date"] >= ts]
    if len(matches) == 0:
        return None
    return int(matches[0])


def event_news_alignment(event_type: EventType, asset: AssetClass, ret_3: float) -> float:
    bias = EVENT_BIAS.get(event_type, {}).get(asset.value, 0.0)
    momentum_sign = 0.0
    if ret_3 > 0:
        momentum_sign = 1.0
    elif ret_3 < 0:
        momentum_sign = -1.0
    return _clip(0.50 + 0.22 * bias * momentum_sign, 0.05, 0.95)


def build_market_state_for_date(
    asset: AssetClass,
    event_type: EventType,
    df: pd.DataFrame,
    idx: int,
) -> MarketState | None:
    if idx < 60:
        return None
    row = df.iloc[idx]
    prev_window = df.iloc[max(0, idx - 60): idx + 1].copy()
    if len(prev_window) < 40:
        return None

    close = float(row["close"])
    ret_3 = float(row.get("ret_3", 0.0) or 0.0)
    ret_5 = float(row.get("ret_5", 0.0) or 0.0)
    ret_20 = float(row.get("ret_20", 0.0) or 0.0)
    vol_20 = float(row.get("vol_20", np.nan))
    vol_60 = float(row.get("vol_60", np.nan))
    atr_14 = float(row.get("atr_14", np.nan))
    rsi_14 = float(row.get("rsi_14", np.nan))
    ema_5 = float(row.get("ema_5", np.nan))
    ema_20 = float(row.get("ema_20", np.nan))
    volume_ratio = float(row.get("volume_ratio", np.nan))

    if not np.isfinite(vol_20) or vol_20 <= 0:
        return None
    if not np.isfinite(vol_60) or vol_60 <= 0:
        vol_60 = vol_20
    if not np.isfinite(atr_14) or atr_14 <= 0:
        atr_14 = close * max(vol_20 * 2.5, 0.005)
    if not np.isfinite(rsi_14):
        rsi_14 = 50.0

    daily_signal = ret_5 / max(vol_20 * math.sqrt(5.0), 1e-6)
    momentum_score = _clip(_sigmoid(daily_signal / 1.8), 0.05, 0.95)

    trend_dir = 0.0
    if np.isfinite(ema_5) and np.isfinite(ema_20) and ema_20 != 0:
        trend_dir = (ema_5 - ema_20) / ema_20
    trend_persistence = _clip(0.50 + 3.0 * trend_dir + 0.8 * ret_20, 0.05, 0.95)

    reversal_score = _clip(max(0.0, abs(rsi_14 - 50.0) - 10.0) / 40.0, 0.0, 0.95)
    atr_pct = atr_14 / max(close, 1e-6)
    volatility_z = _clip(((vol_20 / max(vol_60, 1e-6)) - 1.0) * 3.0 + 1.0, 0.0, 5.0)

    if np.isfinite(volume_ratio):
        liquidity_score = _clip(0.35 + 0.25 * min(volume_ratio, 2.0) + 0.25 * (1.0 - min(atr_pct * 25.0, 1.0)), 0.05, 0.95)
    else:
        liquidity_score = _clip(0.72 - min(atr_pct * 18.0, 0.55), 0.20, 0.90)

    spread_bps = _clip(atr_pct * 1200.0, 2.0, 80.0)
    execution_quality = _clip(
        0.55 * liquidity_score
        + 0.25 * (1.0 - min(volatility_z / 5.0, 1.0))
        + 0.20 * (1.0 - min(spread_bps / 80.0, 1.0)),
        0.05,
        0.95,
    )
    breakout_quality = _clip(0.45 + 0.25 * momentum_score + 0.20 * trend_persistence - 0.10 * reversal_score, 0.05, 0.95)
    orderbook_pressure = _clip(0.50 + daily_signal * 0.10, 0.05, 0.95)
    news_alignment = event_news_alignment(event_type, asset, ret_3)

    return MarketState(
        asset=asset,
        symbol=ASSET_CONFIG[asset]["symbol"],
        timestamp_utc=pd.Timestamp(row["date"]).to_pydatetime().replace(tzinfo=timezone.utc),
        price=close,
        spread_bps=spread_bps,
        volatility_z=volatility_z,
        momentum_score=momentum_score,
        reversal_score=reversal_score,
        liquidity_score=liquidity_score,
        cross_asset_alignment=0.50,
        news_alignment=news_alignment,
        orderbook_pressure=orderbook_pressure,
        trend_persistence=trend_persistence,
        execution_quality=execution_quality,
        breakout_quality=breakout_quality,
        raw={
            "ret_3": ret_3,
            "ret_5": ret_5,
            "ret_20": ret_20,
            "atr_pct": atr_pct,
            "rsi_14": rsi_14,
            "state_date": str(row["date"].date()),
        },
    )


def build_event(event_type: EventType, event_date: date, title: str) -> MacroEvent:
    defaults = EVENT_DEFAULTS.get(event_type, dict(source_confidence=0.70, surprise_score=0.40))
    return MacroEvent(
        event_id=f"{event_type.value}_{event_date.isoformat()}",
        event_type=event_type,
        title=title,
        timestamp_utc=datetime.combine(event_date, datetime.min.time(), tzinfo=timezone.utc),
        source="historical_calendar_validation",
        human_thesis=title,
        expected_assets=[AssetClass.FX, AssetClass.RATES, AssetClass.CRYPTO, AssetClass.OIL, AssetClass.INDEX],
        **defaults,
    )


def wait_to_holding_days(wait_seconds: int) -> int:
    if wait_seconds <= 90:
        return 1
    if wait_seconds <= 180:
        return 2
    if wait_seconds <= 300:
        return 3
    return 5


def evaluate_trade_path(
    df: pd.DataFrame,
    entry_idx: int,
    hold_days: int,
    direction: str,
) -> dict | None:
    exit_idx = min(entry_idx + hold_days, len(df) - 1)
    if exit_idx <= entry_idx:
        return None
    entry = df.iloc[entry_idx]
    horizon = df.iloc[entry_idx: exit_idx + 1]
    entry_price = float(entry["close"])
    exit_price = float(df.iloc[exit_idx]["close"])
    raw_return = (exit_price / entry_price) - 1.0
    if direction == "short":
        pnl_pct = -raw_return * 100.0
        mfe_pct = ((entry_price - float(horizon["low"].min())) / entry_price) * 100.0
        mae_pct = -((float(horizon["high"].max()) - entry_price) / entry_price) * 100.0
    elif direction == "long":
        pnl_pct = raw_return * 100.0
        mfe_pct = ((float(horizon["high"].max()) - entry_price) / entry_price) * 100.0
        mae_pct = -((entry_price - float(horizon["low"].min())) / entry_price) * 100.0
    else:
        pnl_pct = 0.0
        mfe_pct = 0.0
        mae_pct = 0.0

    atr_pct = float(entry.get("atr_14", np.nan)) / max(entry_price, 1e-6)
    if not np.isfinite(atr_pct) or atr_pct <= 0:
        atr_pct = max(abs(raw_return), 0.005)
    r_multiple = (pnl_pct / 100.0) / atr_pct
    return {
        "entry_date": str(pd.Timestamp(entry["date"]).date()),
        "exit_date": str(pd.Timestamp(df.iloc[exit_idx]["date"]).date()),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "underlying_return_pct": raw_return * 100.0,
        "pnl_pct": pnl_pct,
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "r_multiple": r_multiple,
        "hold_days": hold_days,
    }


def confidence_label(x: float) -> str:
    if x >= 0.85:
        return "strong"
    if x >= 0.72:
        return "healthy"
    if x >= 0.60:
        return "moderate"
    return "fragile"


def subset_objective(case_asset_pnl: pd.DataFrame, subset: tuple[str, ...]) -> dict:
    frame = case_asset_pnl[list(subset)].copy()
    portfolio = frame.sum(axis=1)
    mean_pnl = float(portfolio.mean())
    volatility = float(portfolio.std(ddof=0)) if len(portfolio) > 1 else 0.0
    win_rate = float((portfolio > 0).mean()) if len(portfolio) else 0.0
    corr_penalty = 0.0
    if len(subset) > 1:
        corr = frame.corr().fillna(0.0).abs()
        pairs = []
        for a, b in itertools.combinations(subset, 2):
            pairs.append(float(corr.loc[a, b]))
        if pairs:
            corr_penalty = float(np.mean(pairs)) * 0.35
    size_penalty = 0.08 * max(0, len(subset) - 2)
    objective = mean_pnl - 0.18 * volatility + 8.0 * win_rate - corr_penalty - size_penalty
    return {
        "subset": list(subset),
        "mean_pnl_pct": mean_pnl,
        "pnl_volatility": volatility,
        "win_rate": win_rate,
        "corr_penalty": corr_penalty,
        "size_penalty": size_penalty,
        "objective": objective,
    }


def build_markdown(summary: dict) -> str:
    lines = [
        "# EventAlpha Real-History Validation Report",
        "",
        f"- generated_at: `{summary['generated_at']}`",
        f"- event_cases: **{summary['event_case_count']}**",
        f"- asset_decisions: **{summary['asset_decision_count']}**",
        f"- entry_decisions: **{summary['entry_decision_count']}**",
        f"- selected_portfolio_entries: **{summary['portfolio_entry_count']}**",
        "",
        "## Headline KPIs",
        "",
        f"- all entry win rate: **{summary['headline']['all_entry_win_rate_pct']:.1f}%**",
        f"- all entry avg pnl: **{summary['headline']['all_entry_avg_pnl_pct']:.2f}%**",
        f"- selected portfolio win rate: **{summary['headline']['selected_portfolio_win_rate_pct']:.1f}%**",
        f"- selected portfolio avg pnl: **{summary['headline']['selected_portfolio_avg_pnl_pct']:.2f}%**",
        f"- top-confidence avg pnl: **{summary['headline']['top_confidence_avg_pnl_pct']:.2f}%**",
        f"- top-confidence win rate: **{summary['headline']['top_confidence_win_rate_pct']:.1f}%**",
        "",
        "## Best Exact Asset Subset",
        "",
        f"- subset: **{', '.join(summary['best_exact_subset']['subset'])}**",
        f"- objective: `{summary['best_exact_subset']['objective']:.3f}`",
        f"- mean pnl per case: `{summary['best_exact_subset']['mean_pnl_pct']:.2f}%`",
        f"- win rate: `{summary['best_exact_subset']['win_rate'] * 100:.1f}%`",
        "",
        "## By Asset",
        "",
    ]
    for row in summary["by_asset"]:
        lines.append(
            f"- `{row['asset']}`: entries={row['entry_count']}, win_rate={row['win_rate_pct']:.1f}%, avg_pnl={row['avg_pnl_pct']:.2f}%, avg_conf={row['avg_execution_confidence']:.3f}"
        )
    lines.extend(["", "## By Event Type", ""])
    for row in summary["by_event_type"]:
        lines.append(
            f"- `{row['event_type']}`: entries={row['entry_count']}, win_rate={row['win_rate_pct']:.1f}%, avg_pnl={row['avg_pnl_pct']:.2f}%"
        )
    lines.extend(
        [
            "",
            "## Quantum Value",
            "",
            "- This validation now produces a real historical case-by-asset payoff matrix.",
            "- The strongest immediate IBM Quantum candidate is **asset subset selection** over the five-asset basket, because it is discrete, cross-case, and already has an exact local baseline for comparison.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2022)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--max-eia-cases", type=int, default=80)
    args = parser.parse_args()

    out_dir = BASE / "reports" / "real_history_validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_calendar = build_event_calendar(args.start_year, args.end_year)
    eia_rows = [r for r in raw_calendar if r["event_type"] == EventType.EIA_INVENTORY]
    other_rows = [r for r in raw_calendar if r["event_type"] != EventType.EIA_INVENTORY]
    if len(eia_rows) > args.max_eia_cases:
        step = max(1, len(eia_rows) // args.max_eia_cases)
        eia_rows = eia_rows[::step][:args.max_eia_cases]
    calendar = sorted(other_rows + eia_rows, key=lambda x: (x["event_date"], x["event_type"].value))

    download_start = date(args.start_year, 1, 1) - timedelta(days=120)
    download_end = date(args.end_year, 12, 31) + timedelta(days=20)

    historical_data: dict[AssetClass, pd.DataFrame] = {}
    source_meta: dict[str, str] = {}
    for asset, cfg in ASSET_CONFIG.items():
        ticker, df = download_history(cfg["tickers"], download_start.isoformat(), download_end.isoformat())
        historical_data[asset] = add_indicators(df)
        source_meta[asset.value] = ticker

    learning = LearningEngine(EventMemoryDB(str(BASE / "reports" / "eventalpha_memory.sqlite")))
    brain = EventAlphaBrain(learning, max_account_risk=0.02)
    preferred_assets = load_preferred_assets().get("preferred_assets", [])

    case_rows: list[dict] = []
    case_asset_matrix: list[dict] = []

    for case in calendar:
        event = build_event(case["event_type"], case["event_date"], case["title"])
        states: dict[AssetClass, MarketState] = {}
        pre_indices: dict[AssetClass, int] = {}
        post_indices: dict[AssetClass, int] = {}
        for asset, df in historical_data.items():
            pre_idx = previous_index(df, case["event_date"])
            post_idx = next_index(df, case["event_date"])
            if pre_idx is None or post_idx is None:
                continue
            state = build_market_state_for_date(asset, case["event_type"], df, pre_idx)
            if state is None:
                continue
            states[asset] = state
            pre_indices[asset] = pre_idx
            post_indices[asset] = post_idx

        if len(states) < 5:
            continue

        ranks = brain.rank_assets_for_event(event, states)
        candidate_decisions = []
        decisions_by_asset: dict[str, dict] = {}
        for rank in ranks:
            state = states[rank.asset]
            related = {a.value: s for a, s in states.items() if a != rank.asset}
            decision = brain.decide(event, state, related=related)
            payload = {
                "asset": rank.asset.value,
                "symbol": rank.symbol,
                "rank_score": rank.score,
                "decision": {
                    "action": decision.action.value,
                    "grade": decision.grade.value,
                    "direction": decision.direction.value,
                    "raw_score": decision.raw_score,
                    "calibrated_confidence": decision.calibrated_confidence,
                    "execution_confidence": decision.execution_confidence,
                    "wait_seconds": decision.wait_seconds,
                    "max_risk_fraction": decision.max_risk_fraction,
                    "reasons": decision.reasons,
                    "metadata": decision.metadata,
                },
            }
            candidate_decisions.append(payload)
            decisions_by_asset[rank.asset.value] = payload

        portfolio = select_portfolio_candidates(
            candidate_decisions,
            top_n=max(1, args.top_n),
            preferred_assets=preferred_assets,
        )
        selected_assets = {row["asset"] for row in portfolio["selected"]}

        matrix_row = {
            "case_id": f"{case['event_type'].value}:{case['event_date'].isoformat()}",
            "event_type": case["event_type"].value,
            "event_date": case["event_date"].isoformat(),
        }

        for asset in AssetClass:
            row = decisions_by_asset[asset.value]
            decision = row["decision"]
            df = historical_data[asset]
            realized = evaluate_trade_path(
                df,
                post_indices[asset],
                wait_to_holding_days(int(decision["wait_seconds"])),
                decision["direction"],
            )
            if realized is None:
                continue

            action = decision["action"]
            is_entry = action in ENTRY_ACTIONS
            pnl_pct = float(realized["pnl_pct"]) if is_entry else 0.0
            profitable = bool(pnl_pct > 0.0) if is_entry else False
            matrix_row[asset.value] = pnl_pct if is_entry else 0.0
            case_rows.append(
                {
                    "case_id": matrix_row["case_id"],
                    "event_type": case["event_type"].value,
                    "event_date": case["event_date"].isoformat(),
                    "asset": asset.value,
                    "source_ticker": source_meta[asset.value],
                    "rank_score": row["rank_score"],
                    "action": action,
                    "grade": decision["grade"],
                    "direction": decision["direction"],
                    "execution_confidence": decision["execution_confidence"],
                    "calibrated_confidence": decision["calibrated_confidence"],
                    "wait_seconds": decision["wait_seconds"],
                    "hold_days": realized["hold_days"],
                    "selected_by_portfolio": asset.value in selected_assets,
                    "state_date": states[asset].raw["state_date"],
                    "entry_date": realized["entry_date"],
                    "exit_date": realized["exit_date"],
                    "price": states[asset].price,
                    "predicted_signal_strength": confidence_label(float(decision["execution_confidence"])),
                    "underlying_return_pct": realized["underlying_return_pct"],
                    "pnl_pct": pnl_pct,
                    "mfe_pct": realized["mfe_pct"] if is_entry else 0.0,
                    "mae_pct": realized["mae_pct"] if is_entry else 0.0,
                    "r_multiple": realized["r_multiple"] if is_entry else 0.0,
                    "profitable": profitable,
                }
            )
        case_asset_matrix.append(matrix_row)

    if not case_rows:
        raise SystemExit("No historical validation rows were produced.")

    cases_df = pd.DataFrame(case_rows)
    matrix_df = pd.DataFrame(case_asset_matrix).fillna(0.0)
    entry_df = cases_df[cases_df["action"].isin(sorted(ENTRY_ACTIONS))].copy()
    selected_entry_df = entry_df[entry_df["selected_by_portfolio"]].copy()
    top_conf_df = entry_df[entry_df["execution_confidence"] >= entry_df["execution_confidence"].quantile(0.75)].copy()

    by_asset = (
        entry_df.groupby("asset", as_index=False)
        .agg(
            entry_count=("asset", "size"),
            win_rate_pct=("profitable", lambda s: float(np.mean(s) * 100.0)),
            avg_pnl_pct=("pnl_pct", "mean"),
            avg_r_multiple=("r_multiple", "mean"),
            avg_execution_confidence=("execution_confidence", "mean"),
        )
        .sort_values("avg_pnl_pct", ascending=False)
    )
    by_event = (
        entry_df.groupby("event_type", as_index=False)
        .agg(
            entry_count=("event_type", "size"),
            win_rate_pct=("profitable", lambda s: float(np.mean(s) * 100.0)),
            avg_pnl_pct=("pnl_pct", "mean"),
            avg_r_multiple=("r_multiple", "mean"),
        )
        .sort_values("avg_pnl_pct", ascending=False)
    )

    asset_cols = [a.value for a in AssetClass]
    subset_results = []
    pnl_matrix = matrix_df[asset_cols].copy()
    for r in range(1, len(asset_cols) + 1):
        for subset in itertools.combinations(asset_cols, r):
            subset_results.append(subset_objective(pnl_matrix, subset))
    subset_results.sort(key=lambda x: x["objective"], reverse=True)
    best_subset = subset_results[0]

    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at": generated_at,
        "date_range": {"start_year": args.start_year, "end_year": args.end_year},
        "source_tickers": source_meta,
        "event_case_count": int(matrix_df["case_id"].nunique()),
        "asset_decision_count": int(len(cases_df)),
        "entry_decision_count": int(len(entry_df)),
        "portfolio_entry_count": int(len(selected_entry_df)),
        "headline": {
            "all_entry_win_rate_pct": float(entry_df["profitable"].mean() * 100.0) if len(entry_df) else 0.0,
            "all_entry_avg_pnl_pct": float(entry_df["pnl_pct"].mean()) if len(entry_df) else 0.0,
            "selected_portfolio_win_rate_pct": float(selected_entry_df["profitable"].mean() * 100.0) if len(selected_entry_df) else 0.0,
            "selected_portfolio_avg_pnl_pct": float(selected_entry_df["pnl_pct"].mean()) if len(selected_entry_df) else 0.0,
            "top_confidence_avg_pnl_pct": float(top_conf_df["pnl_pct"].mean()) if len(top_conf_df) else 0.0,
            "top_confidence_win_rate_pct": float(top_conf_df["profitable"].mean() * 100.0) if len(top_conf_df) else 0.0,
        },
        "best_exact_subset": best_subset,
        "top_5_exact_subsets": subset_results[:5],
        "by_asset": by_asset.to_dict(orient="records"),
        "by_event_type": by_event.to_dict(orient="records"),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"eventalpha_real_history_cases_{stamp}.csv"
    matrix_path = out_dir / f"eventalpha_real_history_matrix_{stamp}.csv"
    json_path = out_dir / f"eventalpha_real_history_summary_{stamp}.json"
    md_path = out_dir / f"eventalpha_real_history_summary_{stamp}.md"

    cases_df.to_csv(csv_path, index=False)
    matrix_df.to_csv(matrix_path, index=False)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    md_path.write_text(build_markdown(summary))

    print("EventAlpha Real-History Validation")
    print("=" * 60)
    print(f"event_cases: {summary['event_case_count']}")
    print(f"asset_decisions: {summary['asset_decision_count']}")
    print(f"entry_decisions: {summary['entry_decision_count']}")
    print(f"selected_portfolio_entries: {summary['portfolio_entry_count']}")
    print("-" * 60)
    print(f"all_entry_win_rate_pct: {summary['headline']['all_entry_win_rate_pct']:.1f}%")
    print(f"all_entry_avg_pnl_pct: {summary['headline']['all_entry_avg_pnl_pct']:.2f}%")
    print(f"selected_portfolio_win_rate_pct: {summary['headline']['selected_portfolio_win_rate_pct']:.1f}%")
    print(f"selected_portfolio_avg_pnl_pct: {summary['headline']['selected_portfolio_avg_pnl_pct']:.2f}%")
    print("-" * 60)
    print(f"best_exact_subset: {best_subset['subset']} | objective={best_subset['objective']:.3f}")
    print(f"cases_csv: {csv_path}")
    print(f"matrix_csv: {matrix_path}")
    print(f"summary_json: {json_path}")
    print(f"summary_md: {md_path}")


if __name__ == "__main__":
    main()
