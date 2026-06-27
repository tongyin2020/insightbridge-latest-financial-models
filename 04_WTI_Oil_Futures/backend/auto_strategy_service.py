"""
WTI Trading Platform - AI Auto Strategy Selector
Analyzes market regime, IV levels, and conditions to recommend optimal options strategy
Uses GPT-4o for intelligent analysis
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AutoStrategySelector:
    """AI-powered options strategy recommendation engine"""

    def __init__(self):
        self.api_key = os.environ.get("EMERGENT_LLM_KEY")
        self._chat = None
        self._session_id = f"auto_strategy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    async def _get_chat(self):
        if self._chat is None:
            try:
                from emergentintegrations.llm.chat import LlmChat
                self._chat = LlmChat(
                    api_key=self.api_key,
                    session_id=self._session_id,
                    system_message="""You are an expert energy futures options strategist specializing in WTI Crude Oil, Brent, and Natural Gas futures options.

Your job is to analyze current market conditions and recommend the BEST options strategy. You have access to these strategies:

1. **Straddle** - Long ATM Call + Put. Best when: expecting large move, low current IV, earnings/event approaching.
2. **Strangle** - Long OTM Call + Put. Best when: similar to straddle but cheaper, slightly less conviction on magnitude.
3. **Iron Condor** - Sell OTM spreads both sides. Best when: range-bound market, high IV (sell premium), low ADX.
4. **Butterfly** - Long wings, short 2x center. Best when: price expected to pin near strike, moderate IV, event risk settling.
5. **Calendar Spread** - Sell near-term, buy far-term same strike. Best when: expecting IV to increase in far-term, stable near-term.
6. **Ratio Spread** - Buy 1 ATM, Sell 2 OTM. Best when: mild directional bias, high IV (collect premium on shorts).

Always respond with valid JSON:
{
  "recommended_strategy": "straddle|strangle|iron_condor|butterfly|calendar_spread|ratio_spread",
  "confidence": 0.0-1.0,
  "direction_bias": "bullish|bearish|neutral",
  "reasoning": "2-3 sentence explanation",
  "risk_level": "low|medium|high",
  "expected_outcome": "brief expected P&L scenario",
  "alternative_strategy": "second-best strategy name",
  "key_factors": ["factor1", "factor2", "factor3"]
}"""
                ).with_model("openai", "gpt-4o")
                logger.info("[AutoStrategy] Initialized OpenAI chat service")
            except Exception as e:
                logger.error(f"[AutoStrategy] Failed to initialize chat: {e}")
                self._chat = None
        return self._chat

    async def recommend_strategy(
        self,
        symbol: str,
        underlying_price: float,
        current_iv: float,
        historical_vol: float,
        iv_percentile: float,
        regime: str,
        adx: float,
        volatility_ratio: float,
        ema_fast: float,
        ema_slow: float,
        recent_price_change_pct: float = 0.0,
    ) -> Dict:
        """Get AI-powered strategy recommendation based on market conditions"""

        # Build market context for the LLM
        market_context = f"""Analyze these current market conditions for {symbol} and recommend the best options strategy:

**Price Data:**
- Current Price: ${underlying_price:.2f}
- EMA Fast (20): ${ema_fast:.2f}
- EMA Slow (50): ${ema_slow:.2f}
- EMA Signal: {"BULLISH (fast > slow)" if ema_fast > ema_slow else "BEARISH (fast < slow)"}
- Recent Price Change: {recent_price_change_pct:.1f}%

**Volatility Data:**
- Current Implied Volatility: {current_iv*100:.1f}%
- Historical Volatility: {historical_vol*100:.1f}%
- IV Percentile: {iv_percentile:.0f}th
- IV vs HV: {"ELEVATED" if current_iv > historical_vol * 1.2 else "DEPRESSED" if current_iv < historical_vol * 0.8 else "FAIR VALUE"}
- Volatility Ratio: {volatility_ratio:.2f}x

**Market Regime:**
- Current Regime: {regime.upper()}
- ADX (Trend Strength): {adx:.1f} {"(Strong trend)" if adx > 28 else "(Weak/no trend)" if adx < 20 else "(Moderate)"}

Recommend the single best strategy and provide your analysis."""

        chat = await self._get_chat()
        if not chat:
            return self._fallback_recommendation(
                current_iv, historical_vol, iv_percentile, regime, adx, volatility_ratio, ema_fast, ema_slow
            )

        try:
            response = await chat.send_message(market_context)
            result = json.loads(response)
            logger.info(f"[AutoStrategy] AI recommended: {result.get('recommended_strategy')}")
            return {
                "source": "ai",
                "symbol": symbol,
                "underlying_price": underlying_price,
                **result,
            }
        except json.JSONDecodeError:
            logger.warning("[AutoStrategy] Failed to parse AI response, using fallback")
            return self._fallback_recommendation(
                current_iv, historical_vol, iv_percentile, regime, adx, volatility_ratio, ema_fast, ema_slow
            )
        except Exception as e:
            logger.error(f"[AutoStrategy] AI error: {e}")
            return self._fallback_recommendation(
                current_iv, historical_vol, iv_percentile, regime, adx, volatility_ratio, ema_fast, ema_slow
            )

    def _fallback_recommendation(
        self,
        current_iv: float,
        historical_vol: float,
        iv_percentile: float,
        regime: str,
        adx: float,
        volatility_ratio: float,
        ema_fast: float,
        ema_slow: float,
    ) -> Dict:
        """Rule-based fallback when AI is unavailable"""

        iv_elevated = current_iv > historical_vol * 1.2
        iv_depressed = current_iv < historical_vol * 0.8
        strong_trend = adx > 28
        weak_trend = adx < 20
        bullish = ema_fast > ema_slow
        high_vol = volatility_ratio > 1.8

        # Decision tree
        if regime == "blocked":
            return self._build_result(
                "iron_condor", 0.6, "neutral", "low",
                "Market is blocked/halted. Iron Condor collects premium while waiting for normalization.",
                "butterfly",
                ["blocked regime", "premium collection", "defined risk"],
            )

        if regime == "event":
            if iv_depressed:
                return self._build_result(
                    "straddle", 0.8, "neutral", "medium",
                    "Event regime with low IV. Straddle captures the expected large move at cheap premium.",
                    "strangle",
                    ["event catalyst", "low IV", "expected large move"],
                )
            else:
                return self._build_result(
                    "strangle", 0.7, "neutral", "medium",
                    "Event regime with elevated IV. Strangle provides cheaper exposure to large moves.",
                    "straddle",
                    ["event catalyst", "high IV makes straddle expensive", "OTM exposure"],
                )

        if iv_elevated and weak_trend:
            return self._build_result(
                "iron_condor", 0.8, "neutral", "low",
                "High IV and weak trend favor selling premium. Iron Condor profits from IV contraction.",
                "calendar_spread",
                ["high IV percentile", "range-bound", "premium selling"],
            )

        if iv_elevated and strong_trend:
            if bullish:
                return self._build_result(
                    "ratio_spread", 0.7, "bullish", "medium",
                    "Strong bullish trend with high IV. Ratio spread captures upside while selling premium.",
                    "calendar_spread",
                    ["strong trend", "high IV", "directional bias"],
                )
            else:
                return self._build_result(
                    "ratio_spread", 0.7, "bearish", "medium",
                    "Strong bearish trend with high IV. Put ratio spread benefits from downside with premium collection.",
                    "calendar_spread",
                    ["strong trend", "high IV", "directional bias"],
                )

        if iv_depressed and weak_trend:
            return self._build_result(
                "calendar_spread", 0.7, "neutral", "low",
                "Low IV and low trend. Calendar spread profits from IV expansion in far-term leg.",
                "straddle",
                ["low IV", "time decay differential", "IV expansion potential"],
            )

        if iv_depressed and strong_trend:
            return self._build_result(
                "straddle", 0.75, "neutral", "medium",
                "Strong trend with depressed IV. Straddle is cheap and trend continuation creates profit.",
                "strangle",
                ["strong directional move", "cheap options", "trend momentum"],
            )

        if not strong_trend and not weak_trend:
            return self._build_result(
                "butterfly", 0.65, "neutral", "low",
                "Moderate conditions favor Butterfly. Price likely to stay near current level.",
                "iron_condor",
                ["moderate ADX", "fair IV", "range expectation"],
            )

        # Default
        return self._build_result(
            "straddle", 0.5, "neutral", "medium",
            "No strong signal. Straddle provides exposure to any large move.",
            "strangle",
            ["uncertain conditions", "volatility exposure", "event hedging"],
        )

    def _build_result(
        self,
        strategy: str,
        confidence: float,
        direction: str,
        risk: str,
        reasoning: str,
        alternative: str,
        factors: list,
    ) -> Dict:
        return {
            "source": "rules",
            "recommended_strategy": strategy,
            "confidence": confidence,
            "direction_bias": direction,
            "reasoning": reasoning,
            "risk_level": risk,
            "expected_outcome": f"Strategy selected based on current market conditions with {confidence*100:.0f}% confidence.",
            "alternative_strategy": alternative,
            "key_factors": factors,
        }


# Global instance
auto_strategy_selector = AutoStrategySelector()
