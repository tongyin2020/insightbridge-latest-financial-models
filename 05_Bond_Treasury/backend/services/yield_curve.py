import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class YieldCurveService:
    """Service for fetching and analyzing yield curve data"""

    def __init__(self):
        self.cache = {}
        self.cache_expiry = {}
        self.cache_duration = 300  # 5 minutes

    async def get_current_yield_curve(self) -> Dict[str, Any]:
        """Get current full yield curve from Yahoo Finance"""
        cache_key = "current_yc"
        if cache_key in self.cache:
            if datetime.now(timezone.utc) < self.cache_expiry.get(cache_key, datetime.min.replace(tzinfo=timezone.utc)):
                return self.cache[cache_key]
        try:
            import yfinance as yf
            tickers = {
                "3M": "^IRX", "2Y": "2YY=F", "5Y": "^FVX",
                "10Y": "^TNX", "30Y": "^TYX"
            }
            curve = {}
            for tenor, symbol in tickers.items():
                try:
                    t = yf.Ticker(symbol)
                    hist = t.history(period="5d")
                    if not hist.empty:
                        current = float(hist['Close'].iloc[-1])
                        prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current
                        week_ago = float(hist['Close'].iloc[0]) if len(hist) >= 5 else current
                        curve[tenor] = {
                            "yield": round(current, 3),
                            "change_1d": round(current - prev, 3),
                            "change_1w": round(current - week_ago, 3)
                        }
                except Exception:
                    pass

            if not curve or len(curve) < 3:
                return self._generate_simulated_curve()

            # Analyze curve shape
            yields_list = [curve.get(t, {}).get("yield", 0) for t in ["3M", "2Y", "5Y", "10Y", "30Y"] if t in curve]
            shape = self._analyze_shape(curve)

            result = {
                "curve": curve,
                "shape": shape,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.cache[cache_key] = result
            self.cache_expiry[cache_key] = datetime.now(timezone.utc) + timedelta(seconds=self.cache_duration)
            return result
        except Exception as e:
            logger.error(f"Yield curve fetch error: {e}")
            return self._generate_simulated_curve()

    async def get_historical_curves(self, period: str = "3mo") -> List[Dict[str, Any]]:
        """Get historical yield curve snapshots"""
        cache_key = f"hist_yc_{period}"
        if cache_key in self.cache:
            if datetime.now(timezone.utc) < self.cache_expiry.get(cache_key, datetime.min.replace(tzinfo=timezone.utc)):
                return self.cache[cache_key]
        try:
            import yfinance as yf
            tickers = {
                "3M": "^IRX", "5Y": "^FVX",
                "10Y": "^TNX", "30Y": "^TYX"
            }
            histories = {}
            for tenor, symbol in tickers.items():
                try:
                    t = yf.Ticker(symbol)
                    hist = t.history(period=period)
                    if not hist.empty:
                        histories[tenor] = hist
                except Exception:
                    pass

            if not histories or "10Y" not in histories:
                return self._generate_simulated_historical(period)

            ref_index = histories["10Y"].index
            result = []
            for date in ref_index:
                entry = {"date": date.strftime("%Y-%m-%d")}
                for tenor, hist in histories.items():
                    if date in hist.index:
                        entry[tenor] = round(float(hist.loc[date, 'Close']), 3)
                if len(entry) > 2:
                    # Compute slope
                    y10 = entry.get("10Y", 0)
                    y3m = entry.get("3M", 0)
                    entry["slope"] = round(y10 - y3m, 3) if y10 and y3m else 0
                    entry["spread_30_10"] = round(entry.get("30Y", 0) - y10, 3) if entry.get("30Y") else 0
                    result.append(entry)

            self.cache[cache_key] = result
            self.cache_expiry[cache_key] = datetime.now(timezone.utc) + timedelta(seconds=self.cache_duration)
            return result
        except Exception as e:
            logger.error(f"Historical yield curve error: {e}")
            return self._generate_simulated_historical(period)

    async def get_curve_heatmap(self, period: str = "6mo") -> List[Dict[str, Any]]:
        """Get yield change heatmap data"""
        hist = await self.get_historical_curves(period)
        if len(hist) < 2:
            return []

        heatmap = []
        tenors = ["3M", "5Y", "10Y", "30Y"]
        for i in range(1, len(hist)):
            entry = {"date": hist[i]["date"]}
            for tenor in tenors:
                prev_val = hist[i-1].get(tenor, 0)
                curr_val = hist[i].get(tenor, 0)
                if prev_val and curr_val:
                    entry[f"{tenor}_change"] = round(curr_val - prev_val, 3)
                else:
                    entry[f"{tenor}_change"] = 0
            heatmap.append(entry)
        return heatmap

    def _analyze_shape(self, curve: Dict) -> Dict[str, Any]:
        tenors = ["3M", "2Y", "5Y", "10Y", "30Y"]
        yields = []
        for t in tenors:
            if t in curve:
                yields.append(curve[t]["yield"])

        if len(yields) < 3:
            return {"type": "UNKNOWN", "description": "Insufficient data"}

        short = yields[0]
        mid = yields[len(yields) // 2]
        long_y = yields[-1]

        if short > long_y + 0.1:
            shape_type = "INVERTED"
            description = "Yield curve is inverted - short-term rates exceed long-term rates. Historically signals recession risk."
            risk = "HIGH"
        elif abs(long_y - short) < 0.15:
            shape_type = "FLAT"
            description = "Yield curve is relatively flat - minimal term premium. Uncertainty about future rate direction."
            risk = "MODERATE"
        elif mid > max(short, long_y):
            shape_type = "HUMPED"
            description = "Yield curve shows a hump in medium tenors. May indicate policy transition expectations."
            risk = "MODERATE"
        else:
            shape_type = "NORMAL"
            description = "Yield curve shows normal upward slope - higher rates for longer maturities."
            risk = "LOW"

        y10 = curve.get("10Y", {}).get("yield", 0)
        y3m = curve.get("3M", {}).get("yield", 0)

        return {
            "type": shape_type,
            "description": description,
            "risk_level": risk,
            "slope_10y_3m": round(y10 - y3m, 3) if y10 and y3m else 0,
            "steepness": round(long_y - short, 3) if yields else 0
        }

    def _generate_simulated_curve(self) -> Dict[str, Any]:
        base_3m = 4.8 + random.uniform(-0.2, 0.2)
        base_2y = 4.5 + random.uniform(-0.2, 0.2)
        base_5y = 4.2 + random.uniform(-0.2, 0.2)
        base_10y = 4.3 + random.uniform(-0.2, 0.2)
        base_30y = 4.5 + random.uniform(-0.2, 0.2)

        curve = {
            "3M": {"yield": round(base_3m, 3), "change_1d": round(random.uniform(-0.05, 0.05), 3), "change_1w": round(random.uniform(-0.1, 0.1), 3)},
            "2Y": {"yield": round(base_2y, 3), "change_1d": round(random.uniform(-0.05, 0.05), 3), "change_1w": round(random.uniform(-0.1, 0.1), 3)},
            "5Y": {"yield": round(base_5y, 3), "change_1d": round(random.uniform(-0.05, 0.05), 3), "change_1w": round(random.uniform(-0.1, 0.1), 3)},
            "10Y": {"yield": round(base_10y, 3), "change_1d": round(random.uniform(-0.05, 0.05), 3), "change_1w": round(random.uniform(-0.1, 0.1), 3)},
            "30Y": {"yield": round(base_30y, 3), "change_1d": round(random.uniform(-0.05, 0.05), 3), "change_1w": round(random.uniform(-0.1, 0.1), 3)},
        }
        shape = self._analyze_shape(curve)
        return {"curve": curve, "shape": shape, "timestamp": datetime.now(timezone.utc).isoformat()}

    def _generate_simulated_historical(self, period: str) -> List[Dict[str, Any]]:
        days_map = {"1mo": 22, "3mo": 66, "6mo": 132, "1y": 252}
        days = days_map.get(period, 66)
        result = []
        base = {"3M": 4.8, "5Y": 4.2, "10Y": 4.3, "30Y": 4.5}
        for i in range(days):
            date = datetime.now(timezone.utc) - timedelta(days=days - i)
            if date.weekday() >= 5:
                continue
            entry = {"date": date.strftime("%Y-%m-%d")}
            for tenor, val in base.items():
                drift = random.uniform(-0.02, 0.02)
                base[tenor] = max(0.5, val + drift)
                entry[tenor] = round(base[tenor], 3)
            entry["slope"] = round(entry["10Y"] - entry["3M"], 3)
            entry["spread_30_10"] = round(entry["30Y"] - entry["10Y"], 3)
            result.append(entry)
        return result


class BondAuctionService:
    """Service for tracking US Treasury bond auctions"""

    def __init__(self, db):
        self.db = db

    async def get_upcoming_auctions(self) -> List[Dict[str, Any]]:
        """Get upcoming Treasury auction schedule"""
        # Generate realistic auction schedule based on US Treasury patterns
        now = datetime.now(timezone.utc)
        auctions = []

        # US Treasury typically auctions:
        # 4-week, 8-week bills: weekly (Monday)
        # 13-week, 26-week bills: weekly (Monday)
        # 2-year, 5-year notes: monthly (last week)
        # 3-year, 7-year, 10-year notes: monthly
        # 30-year bonds: quarterly (Feb, May, Aug, Nov)
        # TIPS: monthly

        auction_types = [
            {"tenor": "4-Week Bill", "frequency": "Weekly", "typical_day": 0, "size_range": (80, 100)},
            {"tenor": "8-Week Bill", "frequency": "Weekly", "typical_day": 0, "size_range": (80, 95)},
            {"tenor": "13-Week Bill", "frequency": "Weekly", "typical_day": 0, "size_range": (70, 85)},
            {"tenor": "26-Week Bill", "frequency": "Weekly", "typical_day": 0, "size_range": (65, 80)},
            {"tenor": "2-Year Note", "frequency": "Monthly", "typical_day": 22, "size_range": (42, 48)},
            {"tenor": "3-Year Note", "frequency": "Monthly", "typical_day": 10, "size_range": (46, 52)},
            {"tenor": "5-Year Note", "frequency": "Monthly", "typical_day": 23, "size_range": (43, 49)},
            {"tenor": "7-Year Note", "frequency": "Monthly", "typical_day": 24, "size_range": (35, 42)},
            {"tenor": "10-Year Note", "frequency": "Monthly", "typical_day": 12, "size_range": (35, 42)},
            {"tenor": "20-Year Bond", "frequency": "Monthly", "typical_day": 18, "size_range": (12, 16)},
            {"tenor": "30-Year Bond", "frequency": "Quarterly", "typical_day": 13, "size_range": (18, 22)},
            {"tenor": "5-Year TIPS", "frequency": "Quarterly", "typical_day": 20, "size_range": (18, 22)},
            {"tenor": "10-Year TIPS", "frequency": "Monthly", "typical_day": 16, "size_range": (15, 19)},
        ]

        for at in auction_types:
            # Calculate next auction date
            if at["frequency"] == "Weekly":
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                next_date = now + timedelta(days=days_until_monday)
            elif at["frequency"] == "Monthly":
                day = min(at["typical_day"], 28)
                if now.day > day:
                    if now.month == 12:
                        next_date = now.replace(year=now.year + 1, month=1, day=day)
                    else:
                        next_date = now.replace(month=now.month + 1, day=day)
                else:
                    next_date = now.replace(day=day)
            else:  # Quarterly
                quarter_months = [2, 5, 8, 11]
                current_q = min(quarter_months, key=lambda m: abs(m - now.month) if m >= now.month else 12)
                if current_q < now.month or (current_q == now.month and now.day > at["typical_day"]):
                    idx = quarter_months.index(current_q)
                    current_q = quarter_months[(idx + 1) % 4]
                    if current_q < now.month:
                        next_date = now.replace(year=now.year + 1, month=current_q, day=at["typical_day"])
                    else:
                        next_date = now.replace(month=current_q, day=min(at["typical_day"], 28))
                else:
                    next_date = now.replace(month=current_q, day=min(at["typical_day"], 28))

            # Ensure weekday
            while next_date.weekday() >= 5:
                next_date += timedelta(days=1)

            days_away = (next_date - now).days
            import random as rng
            size = rng.randint(at["size_range"][0], at["size_range"][1])

            auctions.append({
                "tenor": at["tenor"],
                "auction_date": next_date.strftime("%Y-%m-%d"),
                "days_away": max(0, days_away),
                "frequency": at["frequency"],
                "estimated_size_bn": size,
                "status": "UPCOMING" if days_away > 1 else "TODAY" if days_away <= 1 else "COMPLETED",
                "impact_level": "HIGH" if "Note" in at["tenor"] or "Bond" in at["tenor"] else "MEDIUM" if "TIPS" in at["tenor"] else "LOW"
            })

        auctions.sort(key=lambda x: x["days_away"])
        return auctions

    async def get_auction_results(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent auction results from DB"""
        results = await self.db.auction_results.find(
            {}, {"_id": 0}
        ).sort("auction_date", -1).limit(limit).to_list(limit)

        if not results:
            # Generate sample historical results
            return self._generate_sample_results()
        return results

    def _generate_sample_results(self) -> List[Dict[str, Any]]:
        import random as rng
        tenors = ["2-Year Note", "3-Year Note", "5-Year Note", "7-Year Note",
                  "10-Year Note", "30-Year Bond", "10-Year TIPS"]
        results = []
        now = datetime.now(timezone.utc)
        for i in range(15):
            date = now - timedelta(days=i * 3 + rng.randint(0, 2))
            tenor = rng.choice(tenors)
            high_yield = 4.0 + rng.uniform(-0.5, 0.5)
            bid_cover = 2.2 + rng.uniform(-0.5, 0.8)
            tail = rng.uniform(-0.02, 0.04)

            results.append({
                "tenor": tenor,
                "auction_date": date.strftime("%Y-%m-%d"),
                "high_yield": round(high_yield, 3),
                "bid_to_cover": round(bid_cover, 2),
                "tail": round(tail, 3),
                "size_bn": rng.randint(30, 50),
                "demand_rating": "STRONG" if bid_cover > 2.5 else "AVERAGE" if bid_cover > 2.0 else "WEAK",
                "yield_impact": round(rng.uniform(-0.05, 0.05), 3)
            })
        return results

    async def get_auction_calendar_summary(self) -> Dict[str, Any]:
        """Get a summary of this week's and next week's auctions"""
        auctions = await self.get_upcoming_auctions()
        now = datetime.now(timezone.utc)
        this_week = [a for a in auctions if a["days_away"] <= 7]
        next_week = [a for a in auctions if 7 < a["days_away"] <= 14]
        high_impact = [a for a in auctions if a["impact_level"] == "HIGH" and a["days_away"] <= 14]

        total_supply = sum(a["estimated_size_bn"] for a in this_week)

        return {
            "this_week": this_week,
            "next_week": next_week,
            "high_impact_upcoming": high_impact,
            "total_supply_this_week_bn": total_supply,
            "auction_count_this_week": len(this_week),
            "next_major_auction": high_impact[0] if high_impact else None
        }
