from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from eventalpha_core.schema import AssetClass, EventType, MacroEvent, MarketState


@dataclass
class AssetRank:
    asset: AssetClass
    symbol: str
    score: float
    reasons: List[str]


EVENT_ASSET_PRIORS: Dict[EventType, Dict[AssetClass, float]] = {
    EventType.CPI: {AssetClass.FX: .88, AssetClass.RATES: .92, AssetClass.INDEX: .78, AssetClass.CRYPTO: .52, AssetClass.OIL: .35},
    EventType.FOMC: {AssetClass.FX: .85, AssetClass.RATES: .95, AssetClass.INDEX: .82, AssetClass.CRYPTO: .58, AssetClass.OIL: .30},
    EventType.NFP: {AssetClass.FX: .75, AssetClass.RATES: .83, AssetClass.INDEX: .70, AssetClass.CRYPTO: .44, AssetClass.OIL: .28},
    EventType.OPEC: {AssetClass.OIL: .95, AssetClass.FX: .45, AssetClass.RATES: .25, AssetClass.INDEX: .35, AssetClass.CRYPTO: .15},
    EventType.EIA_INVENTORY: {AssetClass.OIL: .90, AssetClass.FX: .30, AssetClass.RATES: .15, AssetClass.INDEX: .20, AssetClass.CRYPTO: .10},
    EventType.GEOPOLITICAL: {AssetClass.OIL: .85, AssetClass.FX: .72, AssetClass.RATES: .70, AssetClass.INDEX: .72, AssetClass.CRYPTO: .55},
    EventType.LIQUIDITY_SHOCK: {AssetClass.FX: .88, AssetClass.RATES: .82, AssetClass.INDEX: .85, AssetClass.CRYPTO: .80, AssetClass.OIL: .45},
}


def rank_assets(event: MacroEvent, states: Dict[AssetClass, MarketState], memory_edges: Dict[AssetClass, float] | None = None) -> List[AssetRank]:
    """Learn-to-rank style asset selector.

    The model ranks where the event is most likely to express clean alpha.
    This is better than forcing a trade in every bot.
    """
    memory_edges = memory_edges or {}
    priors = EVENT_ASSET_PRIORS.get(event.event_type, {})
    ranks: List[AssetRank] = []
    for asset, state in states.items():
        prior = priors.get(asset, .30)
        tradability = 0.30 * state.liquidity_score - 0.15 * min(state.spread_bps / 30.0, 1.0)
        confirmation = 0.22 * state.cross_asset_alignment + 0.18 * state.news_alignment + 0.18 * state.momentum_score - 0.12 * state.reversal_score
        memory = 0.12 * memory_edges.get(asset, 0.50)
        score = max(0.0, min(1.0, 0.35 * prior + tradability + confirmation + memory))
        ranks.append(AssetRank(asset=asset, symbol=state.symbol, score=score, reasons=[
            f"event_asset_prior={prior:.2f}", f"liquidity={state.liquidity_score:.2f}",
            f"spread_bps={state.spread_bps:.1f}", f"momentum={state.momentum_score:.2f}",
            f"cross_asset={state.cross_asset_alignment:.2f}", f"memory_edge={memory_edges.get(asset, .5):.2f}"
        ]))
    return sorted(ranks, key=lambda r: r.score, reverse=True)
