"""
WTI Trading Platform - ML Enhancement Service using OpenAI
"""
import os
import json
import logging
from typing import Optional, Tuple
from datetime import datetime, timezone

from models import Regime, Direction, Indicators, MLPrediction

logger = logging.getLogger(__name__)


class MLEnhancementService:
    """ML-enhanced regime detection and signal confidence scoring using OpenAI"""
    
    def __init__(self):
        self.api_key = os.environ.get('EMERGENT_LLM_KEY')
        self._chat = None
        self._session_id = f"wti_ml_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    
    async def _get_chat(self):
        if self._chat is None:
            try:
                from emergentintegrations.llm.chat import LlmChat
                self._chat = LlmChat(
                    api_key=self.api_key,
                    session_id=self._session_id,
                    system_message="""You are an expert WTI crude oil futures trading analyst. 
Your role is to analyze market indicators and provide regime predictions and signal confidence scores.

Market Regimes:
- NORMAL: Regular market conditions, standard volatility
- EVENT: High-impact news/event just occurred (EIA, OPEC, geopolitical)
- TREND: Strong directional trend established (ADX > 28, consistent EMA alignment)
- BLOCKED: Extreme volatility or abnormal conditions, trading should stop

Always respond with valid JSON containing:
{
  "predicted_regime": "normal|event|trend|blocked",
  "regime_confidence": 0.0-1.0,
  "signal_direction": "long|short|none",
  "signal_confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}"""
                ).with_model("openai", "gpt-4o")
                logger.info("[ML] Initialized OpenAI chat service")
            except Exception as e:
                logger.error(f"[ML] Failed to initialize chat: {e}")
                self._chat = None
        return self._chat
    
    async def analyze_market(
        self,
        indicators: Indicators,
        current_price: float,
        recent_event: Optional[str] = None,
        current_regime: Optional[Regime] = None,
    ) -> MLPrediction:
        """Analyze market conditions and return ML-enhanced predictions"""
        
        try:
            chat = await self._get_chat()
            if chat is None:
                return self._fallback_prediction(indicators, current_regime)
            
            from emergentintegrations.llm.chat import UserMessage
            
            prompt = f"""Analyze these WTI crude oil market conditions:

CURRENT INDICATORS:
- Price: ${current_price:.2f}
- EMA Fast (20): {indicators.ema_fast:.2f}
- EMA Slow (50): {indicators.ema_slow:.2f}
- ADX: {indicators.adx:.2f}
- ATR: {indicators.atr:.4f}
- ATR Baseline: {indicators.atr_baseline:.4f}
- Volatility Ratio: {indicators.volatility_ratio:.2f}
- VWAP: {indicators.vwap:.2f}
- Volume Ratio: {indicators.volume_ratio:.2f}

CURRENT STATE:
- Current Regime: {current_regime.value if current_regime else 'unknown'}
- Recent Event: {recent_event or 'None'}

EMA Alignment: {'Bullish (fast > slow)' if indicators.ema_fast > indicators.ema_slow else 'Bearish (fast < slow)'}
Trend Strength: {'Strong' if indicators.adx > 28 else 'Moderate' if indicators.adx > 22 else 'Weak'}
Volatility: {'Extreme' if indicators.volatility_ratio > 4 else 'High' if indicators.volatility_ratio > 1.8 else 'Normal'}

Based on this analysis, provide your regime prediction and signal recommendation."""

            message = UserMessage(text=prompt)
            response = await chat.send_message(message)
            
            return self._parse_response(response, indicators, current_regime)
            
        except Exception as e:
            logger.error(f"[ML] Analysis error: {e}")
            return self._fallback_prediction(indicators, current_regime)
    
    def _parse_response(self, response: str, indicators: Indicators, current_regime: Optional[Regime]) -> MLPrediction:
        """Parse the LLM response into MLPrediction"""
        try:
            # Try to extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                
                regime_map = {
                    "normal": Regime.NORMAL,
                    "event": Regime.EVENT,
                    "trend": Regime.TREND,
                    "blocked": Regime.BLOCKED,
                }
                
                direction_map = {
                    "long": Direction.LONG,
                    "short": Direction.SHORT,
                    "none": None,
                }
                
                predicted_regime = regime_map.get(
                    data.get("predicted_regime", "normal").lower(),
                    Regime.NORMAL
                )
                
                signal_dir_str = data.get("signal_direction", "none")
                signal_direction = direction_map.get(
                    signal_dir_str.lower() if signal_dir_str else "none",
                    None
                )
                
                return MLPrediction(
                    predicted_regime=predicted_regime,
                    confidence=float(data.get("regime_confidence", 0.5)),
                    signal_direction=signal_direction,
                    signal_confidence=float(data.get("signal_confidence", 0.0)),
                    reasoning=data.get("reasoning", "AI analysis complete"),
                )
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"[ML] Failed to parse response: {e}")
        
        return self._fallback_prediction(indicators, current_regime)
    
    def _fallback_prediction(self, indicators: Indicators, current_regime: Optional[Regime]) -> MLPrediction:
        """Fallback prediction when ML service is unavailable"""
        
        # Rule-based prediction
        predicted_regime = Regime.NORMAL
        confidence = 0.6
        signal_direction = None
        signal_confidence = 0.0
        
        # Check for blocked conditions
        if indicators.volatility_ratio > 4.0:
            predicted_regime = Regime.BLOCKED
            confidence = 0.9
        # Check for trend
        elif indicators.adx > 28:
            predicted_regime = Regime.TREND
            confidence = 0.75
            if indicators.ema_fast > indicators.ema_slow:
                signal_direction = Direction.LONG
                signal_confidence = min(0.7, indicators.adx / 40)
            else:
                signal_direction = Direction.SHORT
                signal_confidence = min(0.7, indicators.adx / 40)
        # Check EMA alignment for direction hint
        elif indicators.adx > 22:
            if indicators.ema_fast > indicators.ema_slow:
                signal_direction = Direction.LONG
                signal_confidence = 0.5
            else:
                signal_direction = Direction.SHORT
                signal_confidence = 0.5
        
        return MLPrediction(
            predicted_regime=predicted_regime,
            confidence=confidence,
            signal_direction=signal_direction,
            signal_confidence=signal_confidence,
            reasoning="Rule-based fallback analysis (ML service unavailable)",
        )
    
    async def get_market_insight(self, question: str) -> str:
        """Get market insight for a specific question"""
        try:
            chat = await self._get_chat()
            if chat is None:
                return "ML service unavailable"
            
            from emergentintegrations.llm.chat import UserMessage
            message = UserMessage(text=question)
            response = await chat.send_message(message)
            return response
            
        except Exception as e:
            logger.error(f"[ML] Insight error: {e}")
            return f"Error: {str(e)}"
