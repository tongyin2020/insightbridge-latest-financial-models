from __future__ import annotations

from typing import Dict

from .schema import AssetClass, Direction, MarketState


def infer_direction(state: MarketState) -> Direction:
    if state.momentum_score >= 0.62 and state.news_alignment >= 0.55:
        return Direction.LONG
    if state.momentum_score <= 0.38 and state.news_alignment <= 0.45:
        return Direction.SHORT
    return Direction.FLAT


def cross_asset_score(primary: MarketState, related: Dict[str, MarketState]) -> float:
    """Score whether related markets confirm the primary trade.

    Examples:
    - FX: DXY and yields should not contradict.
    - Rates: 2Y/10Y and real-yield proxy should align.
    - Oil: Brent/WTI and USD should not contradict.
    - Index: VIX, yields, NQ/ES breadth should align.
    - Crypto: BTC/ETH/funding/OI should align.
    """
    if not related:
        return primary.cross_asset_alignment
    scores = [primary.cross_asset_alignment]
    for s in related.values():
        scores.append(s.cross_asset_alignment)
        scores.append(1.0 - s.reversal_score)
        scores.append(s.liquidity_score)
    return max(0.0, min(1.0, sum(scores) / len(scores)))
