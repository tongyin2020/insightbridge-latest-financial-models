from __future__ import annotations

from .schema import AssetClass, EventType, MacroEvent, MarketState


BASE_WAIT = {
    EventType.CPI: (30, 180),
    EventType.FOMC: (180, 1800),
    EventType.NFP: (60, 300),
    EventType.TREASURY_AUCTION: (120, 600),
    EventType.OPEC: (300, 1800),
    EventType.EIA_INVENTORY: (120, 900),
    EventType.GEOPOLITICAL: (60, 900),
    EventType.LIQUIDITY_SHOCK: (300, 3600),
    EventType.REGULATORY: (180, 1800),
    EventType.EARNINGS_SHOCK: (300, 1800),
    EventType.UNKNOWN: (300, 1800),
}

ASSET_MULTIPLIER = {
    AssetClass.FX: 0.8,
    AssetClass.RATES: 1.3,
    AssetClass.CRYPTO: 0.9,
    AssetClass.OIL: 1.2,
    AssetClass.INDEX: 1.1,
}


def recommended_wait_seconds(event: MacroEvent, state: MarketState, memory_wait_seconds: int | None = None) -> int:
    lo, hi = BASE_WAIT.get(event.event_type, (300, 1800))
    mid = (lo + hi) / 2
    wait = mid * ASSET_MULTIPLIER.get(state.asset, 1.0)
    if state.volatility_z > 3.0 or state.spread_bps > 15:
        wait *= 1.35
    if state.momentum_score > 0.78 and state.cross_asset_alignment > 0.78 and state.news_alignment > 0.78:
        wait *= 0.75
    if memory_wait_seconds:
        wait = 0.60 * wait + 0.40 * memory_wait_seconds
    return int(max(lo, min(hi, wait)))
