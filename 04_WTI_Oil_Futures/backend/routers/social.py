"""Social/Copy trading routes - Strategy sharing, leaderboard, PvP battles."""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone

from deps import db, get_optional_user, replay_engine
from replay_engine import HISTORICAL_EVENTS

router = APIRouter()


@router.get("/social/leaderboard")
async def get_leaderboard():
    strategies = await db.shared_strategies.find(
        {"public": True}, {"_id": 0}
    ).sort("score", -1).limit(20).to_list(20)
    return {"strategies": strategies}


@router.post("/social/share")
async def share_strategy(request: Request):
    user = await get_optional_user(request)
    body = await request.json()
    name = body.get("name", "Unnamed Strategy")
    description = body.get("description", "")
    config = body.get("config", {})
    performance = body.get("performance", {})
    strategy_id = f"strat_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{name[:10].replace(' ','_')}"
    doc = {
        "id": strategy_id, "name": name, "description": description,
        "config": config, "performance": performance,
        "author": user.get("name", "Anonymous") if user else "Anonymous",
        "author_id": user["_id"] if user else "guest",
        "public": True, "followers": 0,
        "score": performance.get("score", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.shared_strategies.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/social/follow/{strategy_id}")
async def follow_strategy(strategy_id: str, request: Request):
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    strategy = await db.shared_strategies.find_one({"id": strategy_id})
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    existing = await db.followed_strategies.find_one({"user_id": user_id, "strategy_id": strategy_id})
    if existing:
        await db.followed_strategies.delete_one({"user_id": user_id, "strategy_id": strategy_id})
        await db.shared_strategies.update_one({"id": strategy_id}, {"$inc": {"followers": -1}})
        return {"action": "unfollowed", "strategy_id": strategy_id}
    await db.followed_strategies.insert_one({
        "user_id": user_id, "strategy_id": strategy_id,
        "followed_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.shared_strategies.update_one({"id": strategy_id}, {"$inc": {"followers": 1}})
    return {"action": "followed", "strategy_id": strategy_id, "config": strategy.get("config", {})}


@router.get("/social/my-strategies")
async def get_my_strategies(request: Request):
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    strategies = await db.shared_strategies.find(
        {"author_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)
    return {"strategies": strategies}


@router.get("/social/following")
async def get_following(request: Request):
    user = await get_optional_user(request)
    user_id = user["_id"] if user else "guest"
    follows = await db.followed_strategies.find(
        {"user_id": user_id}, {"_id": 0}
    ).to_list(20)
    strategy_ids = [f["strategy_id"] for f in follows]
    if not strategy_ids:
        return {"following": []}
    strategies = await db.shared_strategies.find(
        {"id": {"$in": strategy_ids}}, {"_id": 0}
    ).to_list(20)
    return {"following": strategies}


# ─── PvP Battle ───

@router.post("/social/pvp")
async def create_pvp_battle(request: Request):
    """Run a PvP battle between two strategy configs across selected events."""
    body = await request.json()
    config_a = body.get("config_a")
    config_b = body.get("config_b")
    name_a = body.get("name_a", "Strategy A")
    name_b = body.get("name_b", "Strategy B")
    event_ids = body.get("event_ids", list(HISTORICAL_EVENTS.keys()))

    if not config_a or not config_b:
        raise HTTPException(status_code=400, detail="Both config_a and config_b are required")

    results_a, results_b, per_event = [], [], []

    for eid in event_ids:
        sim_a = replay_engine.simulate_strategy(eid, config_a)
        sim_b = replay_engine.simulate_strategy(eid, config_b)
        if "error" in sim_a or "error" in sim_b:
            continue
        sa, sb = sim_a["summary"], sim_b["summary"]
        results_a.append(sa)
        results_b.append(sb)
        winner = "a" if sa["total_pnl"] > sb["total_pnl"] else ("b" if sb["total_pnl"] > sa["total_pnl"] else "tie")
        per_event.append({
            "event_id": eid, "event_name": sim_a["event"]["name"],
            "a_pnl": sa["total_pnl"], "a_trades": sa["total_trades"], "a_win_rate": sa["win_rate"],
            "b_pnl": sb["total_pnl"], "b_trades": sb["total_trades"], "b_win_rate": sb["win_rate"],
            "winner": winner,
        })

    if not per_event:
        raise HTTPException(status_code=400, detail="No valid events to compare")

    a_total_pnl = sum(r["total_pnl"] for r in results_a)
    b_total_pnl = sum(r["total_pnl"] for r in results_b)
    a_total_trades = sum(r["total_trades"] for r in results_a)
    b_total_trades = sum(r["total_trades"] for r in results_b)
    a_wins = sum(r["winning_trades"] for r in results_a)
    b_wins = sum(r["winning_trades"] for r in results_b)
    a_max_dd = max((r["max_drawdown_pct"] for r in results_a), default=0)
    b_max_dd = max((r["max_drawdown_pct"] for r in results_b), default=0)
    a_events_won = sum(1 for e in per_event if e["winner"] == "a")
    b_events_won = sum(1 for e in per_event if e["winner"] == "b")
    ties = sum(1 for e in per_event if e["winner"] == "tie")
    overall_winner = "a" if a_total_pnl > b_total_pnl else ("b" if b_total_pnl > a_total_pnl else "tie")

    battle_id = f"pvp_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    result = {
        "id": battle_id, "name_a": name_a, "name_b": name_b,
        "config_a": config_a, "config_b": config_b,
        "per_event": per_event,
        "summary_a": {
            "total_pnl": round(a_total_pnl, 2), "total_trades": a_total_trades,
            "win_rate": round(a_wins / a_total_trades * 100, 1) if a_total_trades > 0 else 0,
            "max_drawdown_pct": round(a_max_dd, 2), "events_won": a_events_won,
        },
        "summary_b": {
            "total_pnl": round(b_total_pnl, 2), "total_trades": b_total_trades,
            "win_rate": round(b_wins / b_total_trades * 100, 1) if b_total_trades > 0 else 0,
            "max_drawdown_pct": round(b_max_dd, 2), "events_won": b_events_won,
        },
        "ties": ties, "overall_winner": overall_winner,
        "events_count": len(per_event),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.pvp_battles.insert_one({**result})
    return result


@router.get("/social/pvp/history")
async def get_pvp_history(limit: int = 10):
    battles = await db.pvp_battles.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"battles": battles}


# ─── Strategy Template Market ───

@router.get("/social/templates")
async def get_strategy_templates():
    """Return top strategies formatted as importable templates, sorted by score."""
    strategies = await db.shared_strategies.find(
        {"public": True}, {"_id": 0}
    ).sort("score", -1).limit(30).to_list(30)

    templates = []
    for s in strategies:
        cfg = s.get("config", {})
        if not cfg or not cfg.get("min_confidence"):
            continue
        perf = s.get("performance", {})
        templates.append({
            "id": s["id"],
            "name": s.get("name", "Unnamed"),
            "author": s.get("author", "Anonymous"),
            "description": s.get("description", ""),
            "config": cfg,
            "total_pnl": perf.get("total_pnl", 0),
            "win_rate": perf.get("win_rate", 0),
            "total_trades": perf.get("total_trades", 0),
            "score": s.get("score", 0),
            "followers": s.get("followers", 0),
            "imports": s.get("imports", 0),
            "created_at": s.get("created_at", ""),
        })
    return {"templates": templates}


@router.post("/social/templates/{strategy_id}/import")
async def import_strategy_template(strategy_id: str, request: Request):
    """Record an import action and return the strategy config for use in replay/pvp."""
    strategy = await db.shared_strategies.find_one({"id": strategy_id}, {"_id": 0})
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.shared_strategies.update_one(
        {"id": strategy_id}, {"$inc": {"imports": 1}}
    )
    return {
        "strategy_id": strategy_id,
        "name": strategy.get("name", "Imported"),
        "config": strategy.get("config", {}),
        "performance": strategy.get("performance", {}),
        "imports": strategy.get("imports", 0) + 1,
    }
