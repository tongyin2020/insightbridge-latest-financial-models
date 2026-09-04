from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any, TypedDict

from agent_system.config import AgentConfig
from agent_system.llm import LLMClient
from agent_system.state import BotSnapshot


class CrisisState(TypedDict, total=False):
    config: AgentConfig
    bot_snapshots: dict[str, BotSnapshot]
    gatekeeper: dict[str, Any]
    phase: str
    macro_report: dict[str, Any]
    technical_report: dict[str, Any]
    critic_report: dict[str, Any]
    risk_report: dict[str, Any]
    consensus: dict[str, Any]


def _sentiment_to_direction(sentiment: str) -> str:
    s = (sentiment or "").lower()
    if s in {"risk_on", "bullish", "positive"}:
        return "BUY"
    if s in {"risk_off", "bearish", "negative"}:
        return "SELL"
    return "HOLD"


def macro_agent(state: CrisisState) -> CrisisState:
    """宏观地缘知识检索 Agent：基于新闻影子日志生成方向观点。"""
    cfg = state["config"]
    snapshots = state["bot_snapshots"]
    llm = LLMClient(cfg)
    signals: dict[str, dict[str, Any]] = {}

    for bot_id, snap in snapshots.items():
        symbol_set = set(snap.symbols)
        shadow = snap.shadow_summary
        # We don't re-read logs here; the adapter already aggregated relevant news.
        # Use total/relevant/would_wake counts as a proxy.
        wake_count = shadow.get("news_would_wake", 0)
        relevant = shadow.get("news_relevant", 0)

        if relevant == 0 or wake_count == 0:
            signals[bot_id] = {"direction": "HOLD", "confidence": 0.0, "reason": "无相关宏观新闻信号"}
            continue

    # Better: re-scan actual news records from base dir for category/sentiment.
    from agent_system.utils import recent_jsonl

    base = cfg.base_dir
    news_records = recent_jsonl(base / "reports" / "runtime" / "news_shadow.log", cfg.news_lookback_minutes)

    for bot_id, snap in snapshots.items():
        symbol_set = set(snap.symbols)
        best: tuple[float, str, str] = (0.0, "HOLD", "无匹配新闻")
        for rec in news_records:
            affected = set(rec.get("affected_symbols", []))
            text = rec.get("text", "")
            if not (affected & symbol_set or any(sym in text for sym in symbol_set)):
                continue
            if not (rec.get("would_wake") and rec.get("is_relevant")):
                continue
            direction = _sentiment_to_direction(rec.get("sentiment", ""))
            if direction == "HOLD":
                continue
            conf = float(rec.get("confidence", 0.0))
            if conf > best[0]:
                best = (conf, direction, f"新闻: {rec.get('category')} {rec.get('sentiment')} ({rec.get('reason', '')})")

        # keyword red-team override: if macro_alert_keywords hit hard and we already have a direction, boost confidence
        if best[1] != "HOLD":
            keyword_hits = 0
            for rec in news_records:
                text = f"{rec.get('text', '')} {rec.get('reason', '')}"
                for kw in cfg.macro_alert_keywords:
                    if kw.lower() in text.lower():
                        keyword_hits += 1
            if keyword_hits > 0 and best[0] < 0.9:
                best = (min(0.5 + keyword_hits * 0.05, 0.9), best[1], f"关键词命中 {keyword_hits} 次; " + best[2])

        signals[bot_id] = {
            "direction": best[1],
            "confidence": round(best[0], 3),
            "reason": best[2],
        }

    # Optional LLM summary (only for aggregated reasoning text, not for direction extraction)
    prompt = "基于以下各机器人宏观信号，请用一句话总结当前最可能的宏观主题：\n" + "\n".join(
        f"{k}: {v['direction']} (conf={v['confidence']}) — {v['reason']}" for k, v in signals.items()
    )
    llm_summary = llm.invoke(prompt, system="你是宏观地缘知识检索 Agent，只给出事实性总结，不交易。")

    return {
        **state,
        "macro_report": {
            "signals": signals,
            "summary": llm_summary.content if llm_summary else "宏观信号已聚合（确定性规则）",
        },
    }


def technical_agent(state: CrisisState) -> CrisisState:
    """技术面与历史相似度对齐 Agent：基于 timeseries/microstructure 影子。"""
    cfg = state["config"]
    snapshots = state["bot_snapshots"]
    signals: dict[str, dict[str, Any]] = {}

    for bot_id, snap in snapshots.items():
        shadow = snap.shadow_summary
        ts_rel = shadow.get("timeseries_relevant", 0)
        confirm = shadow.get("timeseries_confirm", 0)
        avg_move = shadow.get("timeseries_avg_expected_move_frac", 0.0)
        fakeout = shadow.get("microstructure_fakeout", 0)
        cvd = shadow.get("microstructure_cvd_divergence", 0)
        liq = shadow.get("microstructure_liquidity_crash", 0)

        if ts_rel == 0:
            signals[bot_id] = {"direction": "HOLD", "confidence": 0.0, "reason": "无时间序列数据"}
            continue

        confirm_ratio = confirm / ts_rel if ts_rel else 0.0

        if fakeout > 0 or liq > 0:
            direction = "HOLD"
            reason = f"微观结构警告: fakeout={fakeout}, liquidity_crash={liq}"
            conf = 0.7
        elif confirm_ratio >= 0.5 and abs(avg_move) > 0.0005:
            direction = "BUY" if avg_move > 0 else "SELL"
            conf = min(confirm_ratio, 0.95)
            reason = f"时序确认率 {confirm_ratio:.0%}，预期移动 {avg_move:.4%}，CVD divergence={cvd}"
        else:
            direction = "HOLD"
            conf = 0.2
            reason = f"时序信号不足: confirm_ratio={confirm_ratio:.0%}, avg_move={avg_move:.4%}"

        signals[bot_id] = {"direction": direction, "confidence": round(conf, 3), "reason": reason}

    return {
        **state,
        "technical_report": {"signals": signals},
    }


def critic_agent(state: CrisisState) -> CrisisState:
    """红队批判 Agent：交叉验证 macro + technical，阻断逻辑幻觉。"""
    cfg = state["config"]
    macro = state.get("macro_report", {}).get("signals", {})
    tech = state.get("technical_report", {}).get("signals", {})
    vetoes: list[dict[str, Any]] = []
    approved: list[str] = []

    for bot_id in set(macro) | set(tech):
        m = macro.get(bot_id, {"direction": "HOLD", "confidence": 0.0})
        t = tech.get(bot_id, {"direction": "HOLD", "confidence": 0.0})

        if m["direction"] == "HOLD" and t["direction"] == "HOLD":
            vetoes.append({"bot_id": bot_id, "reason": "双方均建议观望"})
            continue
        if cfg.critic_need_agreement and m["direction"] != t["direction"]:
            vetoes.append({"bot_id": bot_id, "reason": f"宏观({m['direction']})与技术({t['direction']})方向冲突"})
            continue
        max_conf = max(m["confidence"], t["confidence"])
        if max_conf < cfg.critic_min_confidence:
            vetoes.append({"bot_id": bot_id, "reason": "双方置信度均低于阈值"})
            continue
        approved.append(bot_id)

    return {
        **state,
        "critic_report": {
            "approved": approved,
            "vetoes": vetoes,
            "note": f"{len(approved)} 个机器人通过批判校验，{len(vetoes)} 个被否决",
        },
    }


def risk_agent(state: CrisisState) -> CrisisState:
    """极端尾部风险控制 Agent：用确定性公式卡死头寸上限。"""
    cfg = state["config"]
    snapshots = state["bot_snapshots"]
    crisis_score = state.get("gatekeeper", {}).get("score", 0.0)
    critic = state.get("critic_report", {})
    approved = set(critic.get("approved", []))
    risk: dict[str, dict[str, Any]] = {}

    for bot_id, snap in snapshots.items():
        if bot_id not in approved:
            risk[bot_id] = {"allowed": False, "size_multiplier": 0.0, "reason": "未通过批判校验"}
            continue

        multiplier = 1.0

        # Recent losing streak penalty
        recent_closed = [t for t in [snap.latest_trade] if t and t.get("status") == "CLOSED"]
        if hasattr(snap, "recent_pnl_pct") and snap.recent_pnl_pct is not None:
            if snap.recent_pnl_pct < -0.05:
                multiplier *= 0.5

        # Open position concentration
        if len(snap.open_positions) >= cfg.risk_max_open_positions:
            multiplier *= 0.5

        # Crisis scale cap
        if crisis_score > 0.8:
            multiplier = min(multiplier, cfg.risk_crisis_scale_cap)

        base_size = cfg.default_position_size.get(bot_id, 1.0)
        final_size = round(base_size * max(multiplier, 0.1), 4)

        risk[bot_id] = {
            "allowed": True,
            "size_multiplier": round(multiplier, 2),
            "suggested_size": final_size,
            "base_size": base_size,
            "reason": f"危机分数={crisis_score:.3f}, 开仓数={len(snap.open_positions)}, size_multiplier={multiplier:.2f}",
        }

    return {
        **state,
        "risk_report": {"bots": risk},
    }


def consensus_node(state: CrisisState) -> CrisisState:
    """汇总四个 Agent 输出，形成最终建议。Phase 1 仍只产生建议，不执行。"""
    cfg = state["config"]
    macro = state.get("macro_report", {}).get("signals", {})
    tech = state.get("technical_report", {}).get("signals", {})
    risk = state.get("risk_report", {}).get("bots", {})
    approved = state.get("critic_report", {}).get("approved", [])

    actions: list[dict[str, Any]] = []
    for bot_id in approved:
        r = risk.get(bot_id, {})
        if not r.get("allowed"):
            continue
        m_dir = macro.get(bot_id, {}).get("direction", "HOLD")
        t_dir = tech.get(bot_id, {}).get("direction", "HOLD")
        direction = t_dir if m_dir == "HOLD" else m_dir
        if direction == "HOLD":
            continue
        conf = min(
            macro.get(bot_id, {}).get("confidence", 0.0),
            tech.get(bot_id, {}).get("confidence", 0.0),
        )
        actions.append({
            "bot_id": bot_id,
            "direction": direction,
            "confidence": round(conf, 3),
            "suggested_size": r.get("suggested_size"),
            "size_multiplier": r.get("size_multiplier"),
            "symbol": (cfg.bot_symbols.get(bot_id, [None]) or [None])[0],
            "reason": {
                "macro": macro.get(bot_id, {}).get("reason", ""),
                "technical": tech.get(bot_id, {}).get("reason", ""),
                "risk": r.get("reason", ""),
            },
        })

    return {
        **state,
        "consensus": {
            "recommendation": {
                "action": "ENTER" if actions else "HOLD",
                "actions": actions,
                "observe_only": True,
                "execution_enabled": cfg.execution_enabled,
                "note": "Phase 1: 危机研判子图已完成，默认观察模式，不实际下单。",
            },
            "approved_bots": approved,
        },
    }
