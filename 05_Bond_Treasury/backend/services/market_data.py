import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from models.schemas import MarketData

logger = logging.getLogger(__name__)


class MarketDataService:
    def __init__(self):
        self.use_real_data = True
        self.cache = {}
        self.cache_expiry = {}
        self.cache_duration = 60

    async def get_real_market_data(self) -> MarketData:
        try:
            import yfinance as yf
            cache_key = "market_data"
            if cache_key in self.cache:
                if datetime.now(timezone.utc) < self.cache_expiry.get(cache_key, datetime.min.replace(tzinfo=timezone.utc)):
                    return self.cache[cache_key]

            wti = yf.Ticker("CL=F")
            tnx = yf.Ticker("^TNX")
            wti_data = wti.history(period="1d")
            tnx_data = tnx.history(period="1d")

            if wti_data.empty or tnx_data.empty:
                return self.generate_simulated_data()

            wti_price = float(wti_data['Close'].iloc[-1])
            bond_yield = float(tnx_data['Close'].iloc[-1])
            ispread = (wti_price / bond_yield) * 0.85 if bond_yield > 0 else 0
            risk_score = min(100, max(0, random.uniform(10, 40)))

            market_data = MarketData(
                timestamp=datetime.now(timezone.utc),
                wti_price=round(wti_price, 2),
                bond_yield=round(bond_yield, 3),
                ispread=round(ispread, 2),
                risk_score=round(risk_score, 1),
                source="yahoo_finance"
            )

            self.cache[cache_key] = market_data
            self.cache_expiry[cache_key] = datetime.now(timezone.utc) + timedelta(seconds=self.cache_duration)
            return market_data
        except Exception as e:
            logger.error(f"Error fetching real market data: {e}")
            return self.generate_simulated_data()

    def generate_simulated_data(self) -> MarketData:
        base_wti = 75.0
        base_rate = 4.25
        wti = base_wti + random.uniform(-3, 3)
        rate = base_rate + random.uniform(-0.1, 0.1)
        ispread = (wti / rate) * 0.85 if rate > 0 else 0
        risk = random.uniform(0, 100)
        return MarketData(
            timestamp=datetime.now(timezone.utc),
            wti_price=round(wti, 2), bond_yield=round(rate, 3),
            ispread=round(ispread, 2), risk_score=round(risk, 1), source="simulated"
        )

    async def get_historical_data(self, period: str = "1mo") -> List[Dict]:
        try:
            import yfinance as yf
            wti = yf.Ticker("CL=F")
            tnx = yf.Ticker("^TNX")
            wti_hist = wti.history(period=period)
            tnx_hist = tnx.history(period=period)

            if wti_hist.empty or tnx_hist.empty:
                return self.generate_historical_simulated(30)

            common_dates = wti_hist.index.intersection(tnx_hist.index)
            history = []
            for date in common_dates:
                wti_price = float(wti_hist.loc[date, 'Close'])
                bond_yield = float(tnx_hist.loc[date, 'Close'])
                ispread = (wti_price / bond_yield) * 0.85 if bond_yield > 0 else 0
                history.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "wti_price": round(wti_price, 2),
                    "bond_yield": round(bond_yield, 3),
                    "ispread": round(ispread, 2),
                    "wti_change": round(float(wti_hist.loc[date, 'Close'] - wti_hist.loc[date, 'Open']), 2),
                    "bond_change": round(float(tnx_hist.loc[date, 'Close'] - tnx_hist.loc[date, 'Open']), 3)
                })
            return history
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return self.generate_historical_simulated(30)

    def generate_historical_simulated(self, days: int = 30) -> List[Dict]:
        history = []
        base_wti = 72.0
        base_rate = 4.15
        for i in range(days):
            date = datetime.now(timezone.utc) - timedelta(days=days - i)
            wti_trend = 0.1 * i + random.uniform(-2, 2)
            rate_trend = 0.002 * i + random.uniform(-0.05, 0.05)
            wti_price = base_wti + wti_trend
            bond_yield = base_rate + rate_trend
            ispread = (wti_price / bond_yield) * 0.85 if bond_yield > 0 else 0
            history.append({
                "date": date.strftime("%Y-%m-%d"),
                "wti_price": round(wti_price, 2), "bond_yield": round(bond_yield, 3),
                "ispread": round(ispread, 2),
                "wti_change": round(random.uniform(-1.5, 1.5), 2),
                "bond_change": round(random.uniform(-0.03, 0.03), 3)
            })
        return history


class BondAnalyticsService:
    def __init__(self):
        self.cache = {}
        self.cache_expiry = {}
        self.cache_duration = 120

    async def get_bond_analytics(self) -> Dict[str, Any]:
        cache_key = "bond_analytics"
        if cache_key in self.cache:
            if datetime.now(timezone.utc) < self.cache_expiry.get(cache_key, datetime.min.replace(tzinfo=timezone.utc)):
                return self.cache[cache_key]
        try:
            import yfinance as yf
            tickers = {
                "tnx": "^TNX", "tyx": "^TYX", "fvx": "^FVX",
                "irx": "^IRX", "vix": "^VIX", "dxy": "DX-Y.NYB", "tips": "TIP",
            }
            data = {}
            for key, symbol in tickers.items():
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="5d")
                    if not hist.empty:
                        data[key] = {
                            "current": float(hist['Close'].iloc[-1]),
                            "prev": float(hist['Close'].iloc[-2]) if len(hist) > 1 else float(hist['Close'].iloc[-1]),
                            "change": float(hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) if len(hist) > 1 else 0.0
                        }
                except Exception:
                    pass
            analytics = self._compute_analytics(data)
            self.cache[cache_key] = analytics
            self.cache_expiry[cache_key] = datetime.now(timezone.utc) + timedelta(seconds=self.cache_duration)
            return analytics
        except Exception as e:
            logger.error(f"Bond analytics error: {e}")
            return self._generate_simulated_analytics()

    def _compute_analytics(self, data: Dict) -> Dict[str, Any]:
        tnx = data.get("tnx", {})
        tyx = data.get("tyx", {})
        fvx = data.get("fvx", {})
        irx = data.get("irx", {})
        vix = data.get("vix", {})
        dxy = data.get("dxy", {})
        tips = data.get("tips", {})

        yield_10y = tnx.get("current", 4.25)
        yield_30y = tyx.get("current", 4.50)
        yield_5y = fvx.get("current", 4.10)
        yield_3m = irx.get("current", 5.0)
        vix_val = vix.get("current", 18.0)
        dxy_val = dxy.get("current", 104.0)
        tips_val = tips.get("current", 105.0)

        curve_slope = round(yield_10y - yield_3m, 3)
        term_spread = round(yield_30y - yield_10y, 3)
        butterfly = round(2 * yield_10y - yield_5y - yield_30y, 3)
        duration_risk = round(max(0, min(100, (1 / max(yield_10y, 0.1)) * 25)), 1)
        breakeven_inflation = round(max(0, yield_10y - (yield_10y * 0.55)), 3)
        real_yield = round(yield_10y - breakeven_inflation, 3)
        is_inverted = curve_slope < 0

        return {
            "yield_curve": {
                "y3m": round(yield_3m, 3), "y5y": round(yield_5y, 3),
                "y10y": round(yield_10y, 3), "y30y": round(yield_30y, 3),
                "slope_10y_3m": curve_slope, "term_spread_30y_10y": term_spread,
                "butterfly_spread": butterfly, "is_inverted": is_inverted
            },
            "risk_metrics": {
                "duration_risk": duration_risk,
                "vix": round(vix_val, 2), "vix_change": round(vix.get("change", 0), 2),
                "dollar_index": round(dxy_val, 2), "dollar_change": round(dxy.get("change", 0), 2)
            },
            "inflation": {
                "breakeven_inflation": breakeven_inflation,
                "real_yield": real_yield,
                "tips_price": round(tips_val, 2)
            },
            "signals": {
                "curve_inversion": "RECESSION_WARNING" if is_inverted else "NORMAL",
                "volatility_regime": "HIGH" if vix_val > 25 else "ELEVATED" if vix_val > 18 else "LOW",
                "dollar_strength": "STRONG" if dxy_val > 105 else "NEUTRAL" if dxy_val > 98 else "WEAK",
                "duration_alert": "HIGH_RISK" if duration_risk > 60 else "MODERATE" if duration_risk > 30 else "LOW_RISK"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _generate_simulated_analytics(self) -> Dict[str, Any]:
        y10 = 4.25 + random.uniform(-0.1, 0.1)
        y30 = y10 + 0.25 + random.uniform(-0.05, 0.05)
        y5 = y10 - 0.15 + random.uniform(-0.05, 0.05)
        y3m = y10 + 0.5 + random.uniform(-0.2, 0.2)
        slope = round(y10 - y3m, 3)
        return {
            "yield_curve": {
                "y3m": round(y3m, 3), "y5y": round(y5, 3),
                "y10y": round(y10, 3), "y30y": round(y30, 3),
                "slope_10y_3m": slope, "term_spread_30y_10y": round(y30 - y10, 3),
                "butterfly_spread": round(2*y10 - y5 - y30, 3), "is_inverted": slope < 0
            },
            "risk_metrics": {
                "duration_risk": round(random.uniform(20, 50), 1),
                "vix": round(random.uniform(14, 28), 2), "vix_change": round(random.uniform(-2, 2), 2),
                "dollar_index": round(random.uniform(100, 108), 2), "dollar_change": round(random.uniform(-0.5, 0.5), 2)
            },
            "inflation": {
                "breakeven_inflation": round(random.uniform(2.0, 2.8), 3),
                "real_yield": round(random.uniform(1.0, 2.0), 3),
                "tips_price": round(random.uniform(102, 108), 2)
            },
            "signals": {
                "curve_inversion": "RECESSION_WARNING" if slope < 0 else "NORMAL",
                "volatility_regime": random.choice(["LOW", "ELEVATED", "HIGH"]),
                "dollar_strength": random.choice(["WEAK", "NEUTRAL", "STRONG"]),
                "duration_alert": random.choice(["LOW_RISK", "MODERATE", "HIGH_RISK"])
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
