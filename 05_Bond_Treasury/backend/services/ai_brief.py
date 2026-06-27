import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)


class AIBriefService:
    """Generates daily AI market commentary using GPT-5.2"""

    def __init__(self, db):
        self.db = db
        self.llm_chat = None
        self.cache = {}
        self.cache_expiry = None

    async def initialize(self):
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if api_key:
            from emergentintegrations.llm.chat import LlmChat
            self.llm_chat = LlmChat(
                api_key=api_key,
                session_id=f"brief-{datetime.now().strftime('%Y%m%d')}",
                system_message="""You are a senior fixed-income analyst at a top investment bank.
                Write concise, professional daily market briefs for bond traders.
                Focus on: yield curve movements, key economic drivers, trading implications.
                Keep the brief under 300 words. Use bullet points for key takeaways.
                Format: Start with a one-line headline, then analysis, then 3-4 actionable insights."""
            ).with_model("openai", "gpt-5.2")

    async def generate_brief(self, market_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate AI market brief from current market data"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check cache (one brief per day)
        if self.cache.get("date") == today and self.cache.get("brief"):
            return self.cache["brief"]

        # Check DB for today's brief
        existing = await self.db.ai_briefs.find_one({"date": today}, {"_id": 0})
        if existing:
            self.cache = {"date": today, "brief": existing}
            return existing

        yc = market_context.get("yield_curve", {})
        rm = market_context.get("risk_metrics", {})
        inf = market_context.get("inflation", {})
        sigs = market_context.get("signals", {})
        auctions = market_context.get("auctions", {})

        prompt = f"""Generate today's bond market brief for {today}:

Market Data:
- 3M Yield: {yc.get('y3m', 'N/A')}%, 5Y: {yc.get('y5y', 'N/A')}%, 10Y: {yc.get('y10y', 'N/A')}%, 30Y: {yc.get('y30y', 'N/A')}%
- Curve Slope (10Y-3M): {yc.get('slope_10y_3m', 'N/A')}%
- Term Spread (30Y-10Y): {yc.get('term_spread_30y_10y', 'N/A')}%
- VIX: {rm.get('vix', 'N/A')}, Dollar Index: {rm.get('dollar_index', 'N/A')}
- Breakeven Inflation: {inf.get('breakeven_inflation', 'N/A')}%
- Real Yield: {inf.get('real_yield', 'N/A')}%
- Signals: Curve={sigs.get('curve_inversion', 'N/A')}, Vol={sigs.get('volatility_regime', 'N/A')}, USD={sigs.get('dollar_strength', 'N/A')}
- This week's auctions: {auctions.get('auction_count_this_week', 'N/A')} scheduled, ${auctions.get('total_supply_this_week_bn', 'N/A')}B supply

Provide a professional daily brief with headline, analysis, and actionable insights."""

        brief_content = ""
        if self.llm_chat:
            try:
                from emergentintegrations.llm.chat import UserMessage
                brief_content = await self.llm_chat.send_message(UserMessage(text=prompt))
            except Exception as e:
                logger.error(f"AI brief generation error: {e}")

        if not brief_content:
            brief_content = self._generate_fallback_brief(market_context, today)

        # Parse headline from content
        lines = brief_content.strip().split('\n')
        headline = lines[0].strip().lstrip('#').strip() if lines else "Daily Bond Market Update"
        body = '\n'.join(lines[1:]).strip() if len(lines) > 1 else brief_content

        brief = {
            "date": today,
            "headline": headline,
            "body": body,
            "market_snapshot": {
                "y10": yc.get("y10y", 0),
                "slope": yc.get("slope_10y_3m", 0),
                "vix": rm.get("vix", 0),
                "curve_signal": sigs.get("curve_inversion", "N/A"),
                "vol_regime": sigs.get("volatility_regime", "N/A")
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ai_generated": bool(self.llm_chat)
        }

        # Store in DB
        await self.db.ai_briefs.update_one(
            {"date": today}, {"$set": brief}, upsert=True
        )
        self.cache = {"date": today, "brief": brief}
        return brief

    def _generate_fallback_brief(self, ctx: Dict, date: str) -> str:
        yc = ctx.get("yield_curve", {})
        rm = ctx.get("risk_metrics", {})
        slope = yc.get("slope_10y_3m", 0)
        vix = rm.get("vix", 18)
        y10 = yc.get("y10y", 4.3)

        if slope < 0:
            curve_note = "The yield curve remains inverted, maintaining recession warning signals."
        elif slope < 0.2:
            curve_note = "The yield curve is nearly flat, suggesting uncertainty about future growth."
        else:
            curve_note = "The yield curve maintains a normal upward slope, supporting risk-on sentiment."

        vol_note = "Elevated VIX suggests caution." if vix > 20 else "Low volatility favors carry trades."

        return f"""Bond Market Daily Brief - {date}

{curve_note} The 10-year Treasury yield stands at {y10:.3f}%. {vol_note}

Key Observations:
- Curve slope at {slope:.3f}% indicates {'tightening financial conditions' if slope < 0.3 else 'normal term premium'}
- Market volatility (VIX {vix:.1f}) {'warrants defensive positioning' if vix > 22 else 'supports tactical opportunities'}
- Monitor upcoming Treasury auctions for supply pressure signals

Trading Implications:
- {'Consider duration hedging given flat curve environment' if abs(slope) < 0.3 else 'Normal curve supports duration exposure'}
- {'Reduce risk exposure until volatility subsides' if vix > 25 else 'Maintain current risk allocation'}
- Watch for curve steepening trades if macro data weakens
- Monitor real yield trends for inflation-protected positioning"""
