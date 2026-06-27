"""Strategy replay routes."""
from fastapi import APIRouter, HTTPException, Request

from deps import replay_engine
from replay_engine import HISTORICAL_EVENTS

router = APIRouter()


@router.get("/replay/events")
async def get_replay_events():
    return {"events": replay_engine.get_events_list()}

@router.get("/replay/{event_id}")
async def replay_historical_event(event_id: str):
    result = replay_engine.replay_event(event_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@router.post("/replay/simulate")
async def simulate_replay_strategy(request: Request):
    body = await request.json()
    event_id = body.get("event_id")
    if not event_id:
        raise HTTPException(status_code=400, detail="event_id is required")
    config = body.get("config", {})
    result = replay_engine.simulate_strategy(event_id, config)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result

@router.post("/replay/compare")
async def compare_multi_event_simulation(request: Request):
    """Run strategy simulation across multiple events and return comparison data."""
    body = await request.json()
    event_ids = body.get("event_ids", [])
    config = body.get("config", {})
    if not event_ids:
        event_ids = list(HISTORICAL_EVENTS.keys())
    results = []
    for eid in event_ids:
        sim = replay_engine.simulate_strategy(eid, config)
        if "error" not in sim:
            results.append(sim)
    if not results:
        raise HTTPException(status_code=400, detail="No valid events found")
    # Aggregate comparison
    total_pnl = sum(r["summary"]["total_pnl"] for r in results)
    total_trades = sum(r["summary"]["total_trades"] for r in results)
    total_wins = sum(r["summary"]["winning_trades"] for r in results)
    avg_return = sum(r["summary"]["return_pct"] for r in results) / len(results)
    max_dd = max(r["summary"]["max_drawdown_pct"] for r in results)
    return {
        "config": config or {"min_confidence": 55, "atr_sl_mult": 1.5, "atr_tp1_mult": 2.0, "atr_tp2_mult": 3.5},
        "events_count": len(results),
        "per_event": [
            {
                "event_id": r["event"]["id"],
                "event_name": r["event"]["name"],
                "date": r["event"]["date"],
                "total_trades": r["summary"]["total_trades"],
                "win_rate": r["summary"]["win_rate"],
                "total_pnl": r["summary"]["total_pnl"],
                "return_pct": r["summary"]["return_pct"],
                "max_drawdown_pct": r["summary"]["max_drawdown_pct"],
                "profit_factor": r["summary"]["profit_factor"],
            }
            for r in results
        ],
        "aggregate": {
            "total_pnl": round(total_pnl, 2),
            "total_trades": total_trades,
            "total_wins": total_wins,
            "overall_win_rate": round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0,
            "avg_return_pct": round(avg_return, 2),
            "worst_drawdown_pct": round(max_dd, 2),
        },
    }


@router.post("/replay/optimize")
async def optimize_strategy_params(request: Request):
    """Grid search over parameter combinations to find optimal bot config."""
    body = await request.json()
    event_ids = body.get("event_ids", list(HISTORICAL_EVENTS.keys()))
    # Parameter ranges
    conf_range = body.get("confidence_range", [40, 50, 60, 70])
    sl_range = body.get("sl_range", [1.0, 1.5, 2.0])
    tp1_range = body.get("tp1_range", [1.5, 2.0, 2.5])
    tp2_range = body.get("tp2_range", [3.0, 3.5, 4.0])

    best = None
    all_results = []

    for conf in conf_range:
        for sl in sl_range:
            for tp1 in tp1_range:
                for tp2 in tp2_range:
                    if tp2 <= tp1:
                        continue
                    cfg = {"min_confidence": conf, "atr_sl_mult": sl, "atr_tp1_mult": tp1, "atr_tp2_mult": tp2}
                    total_pnl = 0
                    total_trades = 0
                    total_wins = 0
                    max_dd = 0
                    for eid in event_ids:
                        sim = replay_engine.simulate_strategy(eid, cfg)
                        if "error" not in sim:
                            total_pnl += sim["summary"]["total_pnl"]
                            total_trades += sim["summary"]["total_trades"]
                            total_wins += sim["summary"]["winning_trades"]
                            max_dd = max(max_dd, sim["summary"]["max_drawdown_pct"])
                    win_rate = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0
                    row = {
                        "config": cfg,
                        "total_pnl": round(total_pnl, 2),
                        "total_trades": total_trades,
                        "win_rate": win_rate,
                        "max_drawdown_pct": round(max_dd, 2),
                        "score": round(total_pnl - max_dd * 500, 2),  # risk-adjusted score
                    }
                    all_results.append(row)
                    if best is None or row["score"] > best["score"]:
                        best = row

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "best": best,
        "top_10": all_results[:10],
        "total_combinations": len(all_results),
        "events_tested": len(event_ids),
    }

