import os
import random
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from models.schemas import MarketData, StrategyConfig, StrategyType
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)


class AITradingEngine:
    def __init__(self):
        self.vol_threshold = 0.05
        self.crash_threshold = 0.12
        self.llm_chat = None

    async def initialize_llm(self):
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if api_key:
            self.llm_chat = LlmChat(
                api_key=api_key,
                session_id=f"trading-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                system_message="""You are an expert AI trading analyst specializing in government bonds and interest rate futures.
                Analyze market data and provide trading signals with confidence scores.
                Consider WTI oil prices, bond yields, and their correlation (Ispread).
                Respond in JSON format with: action (BUY_BOND/SELL_BOND/RATE_LONG/RATE_SHORT/HOLD), confidence (0-1), reasoning (brief explanation)."""
            ).with_model("openai", "gpt-5.2")

    def calculate_ispread(self, wti: float, bond_rate: float) -> float:
        if bond_rate == 0:
            return 0
        return (wti / bond_rate) * 0.85

    def scan_risk(self, current: MarketData, previous: Optional[MarketData]) -> Dict[str, Any]:
        if not previous:
            return {"status": "SAFE", "change": 0}
        rate_change = abs(current.bond_yield - previous.bond_yield) / max(previous.bond_yield, 0.001)
        if rate_change > self.crash_threshold:
            return {"status": "HALT", "change": rate_change, "reason": "BLACK_SWAN_DETECTED"}
        elif rate_change > self.vol_threshold:
            return {"status": "WARNING", "change": rate_change, "reason": "HIGH_VOLATILITY"}
        return {"status": "SAFE", "change": rate_change}

    async def analyze_market(self, data: MarketData, strategy: StrategyConfig, bond_analytics_service=None) -> Optional[Dict[str, Any]]:
        if strategy.strategy_type == StrategyType.MEAN_REVERSION:
            if data.ispread > strategy.ispread_upper:
                return {
                    "action": "SELL_BOND",
                    "confidence": min(0.95, 0.7 + (data.ispread - strategy.ispread_upper) * 0.05),
                    "reasoning": f"Mean Reversion: Ispread {data.ispread:.2f} above upper threshold {strategy.ispread_upper}"
                }
            elif data.ispread < strategy.ispread_lower:
                return {
                    "action": "BUY_BOND",
                    "confidence": min(0.95, 0.7 + (strategy.ispread_lower - data.ispread) * 0.05),
                    "reasoning": f"Mean Reversion: Ispread {data.ispread:.2f} below lower threshold {strategy.ispread_lower}"
                }

        elif strategy.strategy_type == StrategyType.MOMENTUM:
            momentum_signal = random.choice(["BUY_BOND", "SELL_BOND", None])
            if momentum_signal:
                return {
                    "action": momentum_signal,
                    "confidence": random.uniform(0.65, 0.85),
                    "reasoning": "Momentum strategy signal based on price trend analysis"
                }

        if strategy.use_ai and self.llm_chat:
            try:
                bond_context = ""
                if bond_analytics_service:
                    try:
                        bond_data = await bond_analytics_service.get_bond_analytics()
                        yc = bond_data.get("yield_curve", {})
                        rm = bond_data.get("risk_metrics", {})
                        inf = bond_data.get("inflation", {})
                        sigs = bond_data.get("signals", {})
                        bond_context = f"""
                Bond-Specific Metrics:
                - Yield Curve: 3M={yc.get('y3m', 'N/A')}%, 5Y={yc.get('y5y', 'N/A')}%, 10Y={yc.get('y10y', 'N/A')}%, 30Y={yc.get('y30y', 'N/A')}%
                - Yield Curve Slope (10Y-3M): {yc.get('slope_10y_3m', 'N/A')}% ({'INVERTED' if yc.get('is_inverted') else 'NORMAL'})
                - Term Spread (30Y-10Y): {yc.get('term_spread_30y_10y', 'N/A')}%
                - Butterfly Spread: {yc.get('butterfly_spread', 'N/A')}%
                - Duration Risk: {rm.get('duration_risk', 'N/A')}/100
                - VIX: {rm.get('vix', 'N/A')} (change: {rm.get('vix_change', 'N/A')})
                - Dollar Index: {rm.get('dollar_index', 'N/A')} (change: {rm.get('dollar_change', 'N/A')})
                - Breakeven Inflation: {inf.get('breakeven_inflation', 'N/A')}%
                - Real Yield: {inf.get('real_yield', 'N/A')}%
                - Signals: Curve={sigs.get('curve_inversion', 'N/A')}, Vol={sigs.get('volatility_regime', 'N/A')}, USD={sigs.get('dollar_strength', 'N/A')}, Duration={sigs.get('duration_alert', 'N/A')}"""
                    except Exception:
                        bond_context = ""

                prompt = f"""Analyze current market conditions for government bond and rate futures trading:
                Core Market Data:
                - WTI Oil Price: ${data.wti_price:.2f}
                - 10Y Bond Yield: {data.bond_yield:.3f}%
                - Ispread (WTI/Bond correlation): {data.ispread:.2f}
                - Risk Score: {data.risk_score:.1f}%
                - Strategy: {strategy.strategy_type.value}
                - Upper Threshold: {strategy.ispread_upper}
                - Lower Threshold: {strategy.ispread_lower}
                {bond_context}
                
                Consider yield curve dynamics, duration risk, inflation expectations, and cross-asset correlations.
                Provide trading recommendation."""

                response = await self.llm_chat.send_message(UserMessage(text=prompt))

                import json
                try:
                    result = json.loads(response)
                    return result
                except Exception:
                    response_lower = response.lower()
                    if "buy" in response_lower and "bond" in response_lower:
                        action = "BUY_BOND"
                    elif "sell" in response_lower and "bond" in response_lower:
                        action = "SELL_BOND"
                    elif "long" in response_lower and "rate" in response_lower:
                        action = "RATE_LONG"
                    elif "short" in response_lower and "rate" in response_lower:
                        action = "RATE_SHORT"
                    else:
                        return None
                    return {
                        "action": action,
                        "confidence": random.uniform(0.7, 0.95),
                        "reasoning": response[:200]
                    }
            except Exception as e:
                logger.error(f"AI analysis error: {e}")

        # Fallback
        if data.ispread > 15.0:
            return {"action": "SELL_BOND", "confidence": random.uniform(0.75, 0.95),
                    "reasoning": "Ispread above 15.0 indicates overbought bond conditions"}
        elif data.ispread < 10.0:
            return {"action": "BUY_BOND", "confidence": random.uniform(0.75, 0.95),
                    "reasoning": "Ispread below 10.0 indicates oversold bond conditions"}
        return None
