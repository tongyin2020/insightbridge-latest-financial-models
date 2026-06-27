"""
AI Market Analyzer using Claude/GPT via Emergent Integrations
Provides intelligent market analysis and trading insights
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage
from models import FeatureSnapshot, SignalCandidate, SystemStateResponse

logger = logging.getLogger(__name__)


class AIMarketAnalyzer:
    """
    AI-powered market analysis using Claude Sonnet
    Provides natural language insights on market conditions
    """
    
    SYSTEM_PROMPT = """You are an expert cryptocurrency trading analyst AI. Your role is to analyze real-time market data for BTC, ETH, and SOL and provide concise, actionable insights.

Your analysis style:
- Be direct and concise (2-3 sentences max per insight)
- Focus on actionable information
- Use professional trading terminology
- Highlight key risk factors
- Never give financial advice, only analysis

When analyzing:
1. Consider the regime state (NORMAL, MOMENTUM, SQUEEZE_RISK, UNSTABLE)
2. Evaluate fragility (LOW, MEDIUM, HIGH)
3. Assess signal quality (direction score, conviction score)
4. Note any concerning patterns

Format your responses as brief terminal-style outputs."""

    def __init__(self):
        self.api_key = os.environ.get('EMERGENT_LLM_KEY')
        self.chat: Optional[LlmChat] = None
        self._initialized = False
    
    def _ensure_initialized(self, session_id: str = "market-analysis"):
        """Initialize the chat client if not already done"""
        if not self._initialized and self.api_key:
            self.chat = LlmChat(
                api_key=self.api_key,
                session_id=session_id,
                system_message=self.SYSTEM_PROMPT
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            self._initialized = True
    
    async def analyze_market_state(
        self,
        symbol: str,
        snapshot: FeatureSnapshot,
        signal: SignalCandidate,
        regime: str,
        fragility: str,
        gate_action: str
    ) -> dict:
        """Generate AI analysis for current market state"""
        
        if not self.api_key:
            return self._generate_fallback_analysis(symbol, snapshot, signal, regime, fragility, gate_action)
        
        try:
            self._ensure_initialized(f"analysis-{symbol}")
            
            prompt = f"""Analyze this {symbol} market snapshot:

PRICE DATA:
- Current Price: ${snapshot.price:,.2f}
- 24h Change: {snapshot.price_change_24h:+.2f}%
- 24h Volume: ${snapshot.volume_24h/1e9:.2f}B

MARKET STRUCTURE:
- Taker Buy Ratio: {snapshot.taker_buy_ratio:.2%}
- Taker Sell Ratio: {snapshot.taker_sell_ratio:.2%}
- Spread Ratio: {snapshot.spread_ratio:.3f}
- OI Delta Ratio: {snapshot.oi_delta_ratio:.3f}
- Funding Rate: {snapshot.funding_rate:.6f}

SYSTEM STATE:
- Regime: {regime}
- Fragility: {fragility}
- Gate Action: {gate_action}

SIGNAL:
- Type: {signal.candidate_type}
- Direction Score: {signal.direction_score:.1f}/100
- Conviction Score: {signal.conviction_score:.1f}/100
- Fragility Score: {signal.fragility_score:.1f}/100

Provide a 2-3 sentence analysis of current conditions and key considerations."""

            user_message = UserMessage(text=prompt)
            response = await self.chat.send_message(user_message)
            
            # Determine sentiment from analysis
            sentiment = self._extract_sentiment(response, signal)
            
            return {
                "symbol": symbol,
                "analysis": response,
                "sentiment": sentiment,
                "confidence": self._calculate_confidence(signal),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return self._generate_fallback_analysis(symbol, snapshot, signal, regime, fragility, gate_action)
    
    def _extract_sentiment(self, analysis: str, signal: SignalCandidate) -> str:
        """Extract sentiment from AI analysis and signal"""
        analysis_lower = analysis.lower()
        
        if signal.side == "LONG" and signal.conviction_score > 60:
            return "BULLISH"
        elif signal.side == "SHORT" and signal.conviction_score > 60:
            return "BEARISH"
        elif "bullish" in analysis_lower or "upward" in analysis_lower:
            return "BULLISH"
        elif "bearish" in analysis_lower or "downward" in analysis_lower:
            return "BEARISH"
        elif "caution" in analysis_lower or "risk" in analysis_lower:
            return "CAUTIOUS"
        else:
            return "NEUTRAL"
    
    def _calculate_confidence(self, signal: SignalCandidate) -> float:
        """Calculate confidence score for the analysis"""
        if signal.candidate_type == "NO_TRADE":
            return 0.3
        
        direction_weight = 0.4
        conviction_weight = 0.4
        fragility_weight = 0.2
        
        # Higher direction deviation from 50 = more confident
        direction_confidence = abs(signal.direction_score - 50) / 50
        conviction_confidence = signal.conviction_score / 100
        fragility_confidence = 1 - (signal.fragility_score / 100)
        
        confidence = (
            direction_confidence * direction_weight +
            conviction_confidence * conviction_weight +
            fragility_confidence * fragility_weight
        )
        
        return min(1.0, max(0.1, confidence))
    
    def _generate_fallback_analysis(
        self,
        symbol: str,
        snapshot: FeatureSnapshot,
        signal: SignalCandidate,
        regime: str,
        fragility: str,
        gate_action: str
    ) -> dict:
        """Generate rule-based analysis when AI is unavailable"""
        
        analyses = []
        
        # Regime analysis
        if regime == "UNSTABLE":
            analyses.append(f"{symbol} showing unstable market conditions. Trading paused.")
        elif regime == "MOMENTUM":
            direction = "bullish" if snapshot.taker_buy_ratio > 0.55 else "bearish"
            analyses.append(f"{symbol} in {direction} momentum regime with elevated activity.")
        elif regime == "SQUEEZE_RISK":
            analyses.append(f"{symbol} squeeze risk detected. High liquidation proximity.")
        else:
            analyses.append(f"{symbol} operating in normal trading conditions.")
        
        # Signal analysis
        if signal.candidate_type == "LONG_CANDIDATE":
            analyses.append(f"Long signal generated with {signal.conviction_score:.0f}% conviction.")
        elif signal.candidate_type == "SHORT_CANDIDATE":
            analyses.append(f"Short signal generated with {signal.conviction_score:.0f}% conviction.")
        else:
            analyses.append("No actionable signal at current levels.")
        
        # Risk note
        if fragility in ["HIGH_FRAGILITY", "MEDIUM_FRAGILITY"]:
            analyses.append(f"Elevated fragility ({fragility.replace('_', ' ').title()}) - reduced position sizing recommended.")
        
        sentiment = "BULLISH" if signal.side == "LONG" else "BEARISH" if signal.side == "SHORT" else "NEUTRAL"
        
        return {
            "symbol": symbol,
            "analysis": " ".join(analyses),
            "sentiment": sentiment,
            "confidence": self._calculate_confidence(signal),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_trading_recommendation(
        self,
        symbol: str,
        signal: SignalCandidate,
        gate_action: str
    ) -> str:
        """Get a brief trading recommendation"""
        
        if gate_action == "FREEZE":
            return "HOLD - System frozen due to market conditions"
        elif gate_action == "BLOCK":
            return "WAIT - Conditions not favorable for entry"
        elif gate_action == "EXIT_NOW":
            return "EXIT - Immediate exit recommended"
        elif gate_action == "ALLOW_REDUCED":
            side = "LONG" if signal.side == "LONG" else "SHORT"
            return f"{side} (REDUCED) - Enter with reduced size"
        elif gate_action == "ALLOW":
            side = "LONG" if signal.side == "LONG" else "SHORT"
            return f"{side} - Full position allowed"
        else:
            return "NEUTRAL - No action"


# Global analyzer instance
ai_analyzer = AIMarketAnalyzer()
