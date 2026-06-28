from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
RUNTIME_DIR = BASE / "reports" / "runtime_logs"
PID_FILE = RUNTIME_DIR / "eventalpha_runtime.pid"
STATE_FILE = RUNTIME_DIR / "eventalpha_runtime_state.json"
RUNS_DIR = BASE / "reports" / "eventalpha_runs"
MEMORY_DB = BASE / "reports" / "eventalpha_memory.sqlite"
REPORTS_DIR = BASE / "reports" / "financial_kpi_reports"

ASSET_ORDER = ["crypto", "fx", "index", "oil", "rates"]
EXPECTED_EVENTS_PER_CYCLE = 7
MODEL_SOURCES = {
    "crypto": "01_Crypto_BTC_ETH_SOL/eventalpha_adapter.py",
    "fx": "03_FX_AUD_NZD_EUR_GBP/backend/eventalpha_adapter.py",
    "index": "02_StockIndex_IBKR_ES_NQ/eventalpha_adapter.py",
    "oil": "04_WTI_Oil_Futures/backend/eventalpha_adapter.py",
    "rates": "05_Bond_Treasury/backend/eventalpha_adapter.py",
}


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def fmt_minutes(dt_text: str | None) -> str:
    if not dt_text:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_text)
    except ValueError:
        return "N/A"
    minutes = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60.0
    if minutes < 1:
        return "<1m"
    if minutes < 60:
        return f"{minutes:.1f}m"
    return f"{minutes/60.0:.1f}h"


def latest_cycle_reports(state: dict) -> list[Path]:
    paths: list[Path] = []
    for result in state.get("results", []):
        saved = result.get("saved_report")
        if saved:
            p = Path(saved)
            if p.exists():
                paths.append(p)
    return paths


def parse_runtime_log() -> dict:
    log_path = RUNTIME_DIR / "eventalpha_runtime.log"
    if not log_path.exists():
        return {
            "cycles": [],
            "events": [],
            "first_cycle_start": None,
            "last_cycle_finish": None,
            "system_availability_pct": None,
        }

    cycle_start_re = r"^\[(?P<ts>.+?) UTC\] cycle (?P<cycle>\d+) start trigger=(?P<trigger>\S+)"
    cycle_finish_re = r"^\[(?P<ts>.+?) UTC\] cycle (?P<cycle>\d+) finish status=(?P<status>\w+) ok=(?P<ok>\d+)/(?P<total>\d+) duration=(?P<dur>[\d.]+)s"
    event_re = r"^\[(?P<ts>.+?) UTC\] event (?P<etype>\S+) ok duration=(?P<dur>[\d.]+)s report=(?P<report>\S+)"
    import re

    cycles = []
    events = []
    starts: dict[int, dict] = {}
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        m = re.match(cycle_start_re, line)
        if m:
            cycle_no = int(m.group("cycle"))
            starts[cycle_no] = {
                "cycle_number": cycle_no,
                "started_at": m.group("ts"),
                "trigger": m.group("trigger"),
            }
            continue
        m = re.match(cycle_finish_re, line)
        if m:
            cycle_no = int(m.group("cycle"))
            payload = starts.get(cycle_no, {}).copy()
            payload.update(
                {
                    "cycle_number": cycle_no,
                    "finished_at": m.group("ts"),
                    "status": m.group("status"),
                    "ok_count": int(m.group("ok")),
                    "event_count": int(m.group("total")),
                    "duration_seconds": float(m.group("dur")),
                }
            )
            cycles.append(payload)
            continue
        m = re.match(event_re, line)
        if m:
            events.append(
                {
                    "finished_at": m.group("ts"),
                    "event_type": m.group("etype"),
                    "duration_seconds": float(m.group("dur")),
                    "report": m.group("report"),
                }
            )

    def parse_utc(text: str | None) -> datetime | None:
        if not text:
            return None
        try:
            return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            return None

    first_start = None
    last_finish = None
    if cycles:
        first_start = min((parse_utc(c.get("started_at")) for c in cycles if c.get("started_at")), default=None)
        last_finish = max((parse_utc(c.get("finished_at")) for c in cycles if c.get("finished_at")), default=None)
    availability = None
    if cycles:
        success_cycles = sum(1 for c in cycles if c.get("status") == "ok")
        availability = round(success_cycles / len(cycles) * 100, 2)
    return {
        "cycles": cycles,
        "events": events,
        "first_cycle_start": first_start,
        "last_cycle_finish": last_finish,
        "system_availability_pct": availability,
    }


def avg(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def flatten_latest_cycle(paths: list[Path]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    candidates: list[dict] = []
    selected: list[dict] = []
    executions: list[dict] = []
    telegram_rows: list[dict] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        event = payload.get("event", {})
        event_type = event.get("event_type")
        for row in payload.get("candidate_decisions", []):
            out = dict(row)
            out["_event_type"] = event_type
            candidates.append(out)
        for row in payload.get("selected_decisions", []):
            out = dict(row)
            out["_event_type"] = event_type
            selected.append(out)
        for row in payload.get("executions", []):
            out = dict(row)
            out["_event_type"] = event_type
            executions.append(out)
        for row in payload.get("telegram_notifications", []):
            out = dict(row)
            out["_event_type"] = event_type
            telegram_rows.append(out)
    return candidates, selected, executions, telegram_rows


def summarize_runtime(state: dict) -> dict:
    pid = None
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None
    return {
        "runner_pid": pid,
        "runner_running": bool(pid and is_running(pid)),
        "cycle_number": state.get("cycle_number"),
        "status": state.get("status"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "duration_seconds": state.get("duration_seconds"),
        "event_count": state.get("event_count"),
        "ok_count": state.get("ok_count"),
        "fail_count": state.get("fail_count"),
        "telegram_alerts": state.get("telegram_alerts"),
    }


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    total = int(round(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def load_historical_db() -> dict[str, dict]:
    summary: dict[str, dict] = {asset: {} for asset in ASSET_ORDER}
    if not MEMORY_DB.exists():
        return summary
    conn = sqlite3.connect(MEMORY_DB)
    try:
        for row in conn.execute(
            """
            SELECT asset, COUNT(*), AVG(entry_confidence), AVG(seconds_waited), AVG(pnl_pct), MAX(created_at)
            FROM event_trades
            GROUP BY asset
            """
        ):
            asset, count_, avg_conf, avg_wait, avg_pnl, latest_ts = row
            summary.setdefault(asset, {}).update(
                {
                    "historical_trades": count_,
                    "historical_avg_entry_confidence": round(avg_conf, 4) if avg_conf is not None else None,
                    "historical_avg_wait_seconds": round(avg_wait, 1) if avg_wait is not None else None,
                    "historical_avg_pnl_pct": round(avg_pnl, 4) if avg_pnl is not None else None,
                    "historical_latest_trade": latest_ts,
                }
            )
        for row in conn.execute(
            """
            SELECT asset, COUNT(*), AVG(memory_edge_delta), AVG(wait_seconds_delta), AVG(risk_multiplier_delta), MAX(created_at)
            FROM learning_updates
            GROUP BY asset
            """
        ):
            asset, count_, avg_edge, avg_wait_delta, avg_risk_delta, latest_ts = row
            summary.setdefault(asset, {}).update(
                {
                    "learning_updates": count_,
                    "avg_memory_edge_delta": round(avg_edge, 4) if avg_edge is not None else None,
                    "avg_wait_seconds_delta": round(avg_wait_delta, 1) if avg_wait_delta is not None else None,
                    "avg_risk_multiplier_delta": round(avg_risk_delta, 4) if avg_risk_delta is not None else None,
                    "latest_learning_update": latest_ts,
                }
            )
    finally:
        conn.close()
    return summary


def summarize_assets(
    candidates: list[dict], selected: list[dict], executions: list[dict], telegram_rows: list[dict], historical: dict[str, dict]
) -> list[dict]:
    by_asset: dict[str, dict] = {asset: {"asset": asset} for asset in ASSET_ORDER}

    cand_map: dict[str, list[dict]] = defaultdict(list)
    sel_map: dict[str, list[dict]] = defaultdict(list)
    exe_map: dict[str, list[dict]] = defaultdict(list)

    for row in candidates:
        cand_map[str(row.get("asset"))].append(row)
    for row in selected:
        sel_map[str(row.get("asset"))].append(row)
    for row in executions:
        exe_map[str(row.get("asset"))].append(row)

    sent_total = sum(1 for row in telegram_rows if row.get("sent"))

    for asset in ASSET_ORDER:
        cands = cand_map.get(asset, [])
        sels = sel_map.get(asset, [])
        exes = exe_map.get(asset, [])
        rank_scores = [float(r.get("rank_score")) for r in cands if isinstance(r.get("rank_score"), (int, float))]
        waits = []
        confs = []
        risks = []
        action_counter = Counter()
        reason_counter = Counter()
        selected_reason_counter = Counter()
        for r in cands:
            decision = r.get("decision", {}) or {}
            if isinstance(decision.get("wait_seconds"), (int, float)):
                waits.append(float(decision["wait_seconds"]))
            if isinstance(decision.get("execution_confidence"), (int, float)):
                confs.append(float(decision["execution_confidence"]) * 100.0)
            if isinstance(decision.get("max_risk_fraction"), (int, float)):
                risks.append(float(decision["max_risk_fraction"]) * 100.0)
            action = decision.get("action")
            if action:
                action_counter[str(action)] += 1
            for reason in decision.get("reasons", []) or []:
                reason_counter[str(reason)] += 1
        for r in sels:
            for reason in ((r.get("decision") or {}).get("reasons", []) or []):
                selected_reason_counter[str(reason)] += 1

        accepted = 0
        execution_status_counter = Counter()
        for e in exes:
            result = e.get("result", {}) or {}
            status = result.get("status")
            if status:
                execution_status_counter[str(status)] += 1
            if str(status).lower() == "accepted":
                accepted += 1

        current_selected_rate = round(len(sels) / len(cands) * 100, 2) if cands else None
        current_accept_rate = round(accepted / len(sels) * 100, 2) if sels else None

        out = by_asset[asset]
        out.update(
            {
                "candidate_events": len(cands),
                "selected_events": len(sels),
                "selected_rate_pct": current_selected_rate,
                "accepted_executions": accepted,
                "accepted_rate_pct": current_accept_rate,
                "avg_rank_score": round(mean(rank_scores), 4) if rank_scores else None,
                "avg_execution_confidence_pct": round(mean(confs), 2) if confs else None,
                "avg_wait_seconds": round(mean(waits), 1) if waits else None,
                "avg_max_risk_fraction_pct": round(mean(risks), 3) if risks else None,
                "top_action": action_counter.most_common(1)[0][0] if action_counter else None,
                "top_candidate_reason": reason_counter.most_common(1)[0][0] if reason_counter else None,
                "top_selected_reason": selected_reason_counter.most_common(1)[0][0] if selected_reason_counter else None,
                "execution_status_summary": dict(execution_status_counter),
                "telegram_sent_total_cycle": sent_total,
            }
        )
        out.update(historical.get(asset, {}))
    return [by_asset[a] for a in ASSET_ORDER]


def summarize_decision_distribution(candidates: list[dict], selected: list[dict]) -> dict:
    candidate_actions = Counter()
    selected_actions = Counter()
    for row in candidates:
        action = (row.get("decision") or {}).get("action")
        if action:
            candidate_actions[str(action)] += 1
    for row in selected:
        action = (row.get("decision") or {}).get("action")
        if action:
            selected_actions[str(action)] += 1
    return {
        "candidate_actions": dict(candidate_actions),
        "selected_actions": dict(selected_actions),
    }


def summarize_decision_reasons(candidates: list[dict], selected: list[dict]) -> dict:
    selected_reason_counter = Counter()
    watch_reason_counter = Counter()
    enter_reason_counter = Counter()

    def normalize(reason: str) -> str:
        prefixes = [
            "regime=",
            "severity=",
            "grade=",
            "posterior=",
            "execution_confidence=",
            "memory_edge=",
            "cross_asset_alignment=",
            "wait_seconds=",
            "direction_or_confidence_not_confirmed",
        ]
        for p in prefixes:
            if reason.startswith(p):
                return p.rstrip("=") if p.endswith("=") else p
        return reason.split(":")[0]

    for row in candidates:
        decision = row.get("decision") or {}
        action = str(decision.get("action") or "")
        reasons = [normalize(str(r)) for r in decision.get("reasons", [])]
        target = watch_reason_counter if action == "watch" else enter_reason_counter
        for r in reasons:
            target[r] += 1
    for row in selected:
        reasons = [normalize(str(r)) for r in (row.get("decision") or {}).get("reasons", [])]
        for r in reasons:
            selected_reason_counter[r] += 1
    return {
        "top_selected_reasons": selected_reason_counter.most_common(10),
        "top_watch_reasons": watch_reason_counter.most_common(10),
        "top_enter_reasons": enter_reason_counter.most_common(10),
    }


def summarize_data_quality(state: dict, reports: list[Path], candidates: list[dict], selected: list[dict], executions: list[dict]) -> dict:
    expected_events = state.get("event_count") or EXPECTED_EVENTS_PER_CYCLE
    report_coverage = len(reports) / expected_events * 100 if expected_events else 0.0
    candidate_completeness = 0.0
    if candidates:
        ok = 0
        for row in candidates:
            d = row.get("decision") or {}
            if row.get("asset") and row.get("symbol") and d.get("action") and d.get("reasons"):
                ok += 1
        candidate_completeness = ok / len(candidates) * 100
    execution_coverage = len(executions) / len(selected) * 100 if selected else 100.0
    event_success = (state.get("ok_count", 0) / expected_events * 100) if expected_events else 0.0
    freshness = 100.0
    if reports:
        latest_mins = min(
            (datetime.now(timezone.utc).timestamp() - p.stat().st_mtime) / 60.0
            for p in reports
        )
        freshness = max(0.0, 100.0 - max(0.0, latest_mins - 30.0))
    score = round(mean([report_coverage, candidate_completeness, execution_coverage, event_success, freshness]), 2)
    return {
        "data_quality_score": score,
        "report_coverage_pct": round(report_coverage, 2),
        "candidate_completeness_pct": round(candidate_completeness, 2),
        "execution_coverage_pct": round(execution_coverage, 2),
        "freshness_score_pct": round(freshness, 2),
    }


def summarize_learning_status(asset_rows: list[dict]) -> dict:
    active_assets = [r for r in asset_rows if (r.get("learning_updates") or 0) > 0]
    latest_updates = [r.get("latest_learning_update") for r in asset_rows if r.get("latest_learning_update")]
    return {
        "assets_with_learning": len(active_assets),
        "total_learning_updates": sum(int(r.get("learning_updates") or 0) for r in asset_rows),
        "avg_memory_edge_delta": avg([float(r["avg_memory_edge_delta"]) for r in asset_rows if isinstance(r.get("avg_memory_edge_delta"), (int, float))]),
        "avg_wait_seconds_delta": avg([float(r["avg_wait_seconds_delta"]) for r in asset_rows if isinstance(r.get("avg_wait_seconds_delta"), (int, float))]),
        "avg_risk_multiplier_delta": avg([float(r["avg_risk_multiplier_delta"]) for r in asset_rows if isinstance(r.get("avg_risk_multiplier_delta"), (int, float))]),
        "latest_learning_update": max(latest_updates) if latest_updates else None,
    }


def summarize_brain_activity(candidates: list[dict], selected: list[dict], executions: list[dict], latest_payloads: list[dict]) -> dict:
    reason_count = sum(len((row.get("decision") or {}).get("reasons", [])) for row in candidates)
    ranking_paths = sum(len(p.get("asset_ranking", [])) for p in latest_payloads)
    regime_snapshots = sum(len(p.get("macro_regime_snapshots", [])) for p in latest_payloads)
    exit_reviews = sum(len(p.get("exit_reviews", [])) for p in latest_payloads)
    return {
        "events_analyzed": len(latest_payloads),
        "candidate_decisions": len(candidates),
        "selected_decisions": len(selected),
        "executions": len(executions),
        "reason_paths_evaluated": reason_count,
        "asset_ranking_paths": ranking_paths,
        "macro_regime_snapshots": regime_snapshots,
        "exit_reviews": exit_reviews,
    }


def summarize_risk_environment(latest_payloads: list[dict]) -> dict:
    prob_acc: defaultdict[str, list[float]] = defaultdict(list)
    for payload in latest_payloads:
        for snap in payload.get("macro_regime_snapshots", []):
            for k, v in (snap.get("macro_regime_probabilities") or {}).items():
                if isinstance(v, (int, float)):
                    prob_acc[str(k)].append(float(v))
    avg_probs = {k: round(mean(v), 4) for k, v in prob_acc.items() if v}
    top = sorted(avg_probs.items(), key=lambda kv: kv[1], reverse=True)[:4]
    high_risk = sum(avg_probs.get(k, 0.0) for k in ["war_shock", "liquidity_crisis", "risk_off", "dollar_squeeze"])
    medium_risk = sum(avg_probs.get(k, 0.0) for k in ["inflation_shock", "growth_shock"])
    if high_risk >= 0.45:
        label = "High"
    elif high_risk + medium_risk >= 0.40:
        label = "Medium"
    else:
        label = "Low"
    return {
        "risk_environment": label,
        "risk_score": round((high_risk * 100.0) + (medium_risk * 50.0), 2),
        "dominant_regime": top[0][0] if top else None,
        "top_macro_regimes": top,
        "avg_macro_regime_probabilities": avg_probs,
    }


def summarize_version_and_health(asset_rows: list[dict], executions: list[dict], candidates: list[dict], data_quality: dict, runtime: dict, log_summary: dict) -> dict:
    exec_adapter_map = {}
    for e in executions:
        asset = str(e.get("asset"))
        adapter = ((e.get("result") or {}).get("adapter"))
        if asset and adapter:
            exec_adapter_map[asset] = adapter
    model_health = []
    for row in asset_rows:
        asset = row["asset"]
        candidate_events = row.get("candidate_events", 0) or 0
        selected_events = row.get("selected_events", 0) or 0
        hist_trades = row.get("historical_trades", 0) or 0
        conf = row.get("avg_execution_confidence_pct")
        components = []
        components.append(100.0 if candidate_events > 0 else 0.0)
        if isinstance(conf, (int, float)):
            components.append(float(conf))
        components.append(100.0 if hist_trades > 0 else 40.0)
        components.append(100.0 if selected_events >= 0 else 0.0)
        health = round(mean(components), 2) if components else None
        status = "healthy" if (health is not None and health >= 80) else "watch"
        model_health.append(
            {
                "asset": asset,
                "health_score": health,
                "status": status,
                "adapter": exec_adapter_map.get(asset, "candidate_only"),
                "source": MODEL_SOURCES.get(asset),
            }
        )
    platform_components = [
        log_summary.get("system_availability_pct") or 0.0,
        data_quality.get("data_quality_score") or 0.0,
        mean([x["health_score"] for x in model_health if isinstance(x.get("health_score"), (int, float))]) if model_health else 0.0,
        100.0 if runtime.get("status") == "ok" else 60.0,
    ]
    platform_score = round(mean(platform_components), 2)
    return {
        "financial_ai_platform_score": platform_score,
        "model_health": model_health,
    }


def write_report(runtime: dict, asset_rows: list[dict], cycle_reports: list[Path], extra: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = REPORTS_DIR / f"financial_model_kpi_report_{ts}.md"
    latest = REPORTS_DIR / "financial_model_kpi_report_latest.md"
    lines = [
        "# InsightBridge Financial Models KPI Report",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- base: `{BASE}`",
        "",
        "## Runtime Status",
        "",
        f"- Runner PID: {runtime['runner_pid'] or 'none'}",
        f"- Runner Running: {runtime['runner_running']}",
        f"- Latest Cycle: {runtime['cycle_number']}",
        f"- Cycle Status: {runtime['status']}",
        f"- Started At: {runtime['started_at']}",
        f"- Finished At: {runtime['finished_at']}",
        f"- Duration Seconds: {runtime['duration_seconds']}",
        f"- Events In Cycle: {runtime['event_count']}",
        f"- Successful Events: {runtime['ok_count']}",
        f"- Failed Events: {runtime['fail_count']}",
        f"- Telegram Alerts Enabled: {runtime['telegram_alerts']}",
        f"- Continuous Runtime: {extra['continuous_runtime_text']}",
        f"- System Availability: {fmt_pct(extra['log_summary'].get('system_availability_pct'))}",
        f"- Financial AI Platform Score: {fmt_num(extra['version_health']['financial_ai_platform_score'])}/100",
        "",
        "## Latest Cycle Reports",
        "",
    ]
    for p in cycle_reports:
        lines.append(f"- `{p.name}`")
    lines.extend(
        [
            "",
            "## New Platform Metrics",
            "",
            f"1. Continuous Runtime: {extra['continuous_runtime_text']}",
            f"2. System Availability: {fmt_pct(extra['log_summary'].get('system_availability_pct'))}",
            f"3. Decision Distribution: candidate={json.dumps(extra['decision_distribution']['candidate_actions'], ensure_ascii=False)} | selected={json.dumps(extra['decision_distribution']['selected_actions'], ensure_ascii=False)}",
            f"4. Decision Reason: selected_top={extra['decision_reasons']['top_selected_reasons'][:5]}",
            f"5. Data Quality Score: {fmt_num(extra['data_quality']['data_quality_score'])}/100",
            f"6. Learning Status: assets_with_learning={extra['learning_status']['assets_with_learning']} | total_updates={extra['learning_status']['total_learning_updates']}",
            f"7. AI Brain Activity: events={extra['brain_activity']['events_analyzed']} | candidates={extra['brain_activity']['candidate_decisions']} | selected={extra['brain_activity']['selected_decisions']} | reasons={extra['brain_activity']['reason_paths_evaluated']}",
            f"8. Risk Environment: {extra['risk_environment']['risk_environment']} | score={fmt_num(extra['risk_environment']['risk_score'])} | top_regimes={extra['risk_environment']['top_macro_regimes']}",
            f"9. Financial AI Platform Score: {fmt_num(extra['version_health']['financial_ai_platform_score'])}/100",
            "10. Version & Model Health:",
        ]
    )
    for row in extra["version_health"]["model_health"]:
        lines.append(f"   - {row['asset']}: {row['status']} | health={fmt_num(row['health_score'])}/100 | adapter={row['adapter']} | source=`{row['source']}`")
    lines.extend(
        [
            "",
            "## Five Financial Models Scorecard",
            "",
            "| Asset Model | Candidate Events | Selected Events | Selected Rate | Accepted Executions | Accepted Rate | Avg Rank Score | Avg Execution Confidence | Avg Wait Seconds | Avg Risk Fraction | Top Action | Historical Trades | Historical Avg PnL |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|",
        ]
    )
    for row in asset_rows:
        lines.append(
            f"| {row['asset']} | {row.get('candidate_events',0)} | {row.get('selected_events',0)} | {fmt_pct(row.get('selected_rate_pct'))} | "
            f"{row.get('accepted_executions',0)} | {fmt_pct(row.get('accepted_rate_pct'))} | {fmt_num(row.get('avg_rank_score'),4)} | "
            f"{fmt_pct(row.get('avg_execution_confidence_pct'))} | {fmt_num(row.get('avg_wait_seconds'),1)} | {fmt_pct(row.get('avg_max_risk_fraction_pct'))} | "
            f"{row.get('top_action') or 'N/A'} | {row.get('historical_trades',0)} | {fmt_pct(row.get('historical_avg_pnl_pct'))} |"
        )
    lines.extend(["", "## Asset Details", ""])
    for row in asset_rows:
        lines.extend(
            [
                f"### {row['asset']}",
                "",
                f"- Candidate Events This Cycle: {row.get('candidate_events',0)}",
                f"- Selected Events This Cycle: {row.get('selected_events',0)}",
                f"- Accepted Executions This Cycle: {row.get('accepted_executions',0)}",
                f"- Average Rank Score: {fmt_num(row.get('avg_rank_score'),4)}",
                f"- Average Execution Confidence: {fmt_pct(row.get('avg_execution_confidence_pct'))}",
                f"- Average Wait Seconds: {fmt_num(row.get('avg_wait_seconds'),1)}",
                f"- Average Max Risk Fraction: {fmt_pct(row.get('avg_max_risk_fraction_pct'))}",
                f"- Top Action: {row.get('top_action') or 'N/A'}",
                f"- Top Candidate Reason: {row.get('top_candidate_reason') or 'N/A'}",
                f"- Top Selected Reason: {row.get('top_selected_reason') or 'N/A'}",
                f"- Historical Trades Logged: {row.get('historical_trades',0)}",
                f"- Historical Avg Entry Confidence: {fmt_num(row.get('historical_avg_entry_confidence'),4)}",
                f"- Historical Avg Wait Seconds: {fmt_num(row.get('historical_avg_wait_seconds'),1)}",
                f"- Historical Avg PnL: {fmt_pct(row.get('historical_avg_pnl_pct'))}",
                f"- Learning Updates: {row.get('learning_updates',0)}",
                f"- Avg Memory Edge Delta: {fmt_num(row.get('avg_memory_edge_delta'),4)}",
                f"- Avg Wait Seconds Delta: {fmt_num(row.get('avg_wait_seconds_delta'),1)}",
                f"- Avg Risk Multiplier Delta: {fmt_num(row.get('avg_risk_multiplier_delta'),4)}",
                "",
            ]
        )
    lines.extend(
        [
            "## Decision Reasons",
            "",
            f"- Top Selected Reasons: {extra['decision_reasons']['top_selected_reasons']}",
            f"- Top Watch Reasons: {extra['decision_reasons']['top_watch_reasons']}",
            f"- Top Enter Reasons: {extra['decision_reasons']['top_enter_reasons']}",
            "",
            "## Data Quality",
            "",
            f"- Data Quality Score: {fmt_num(extra['data_quality']['data_quality_score'])}/100",
            f"- Report Coverage: {fmt_pct(extra['data_quality']['report_coverage_pct'])}",
            f"- Candidate Completeness: {fmt_pct(extra['data_quality']['candidate_completeness_pct'])}",
            f"- Execution Coverage: {fmt_pct(extra['data_quality']['execution_coverage_pct'])}",
            f"- Freshness Score: {fmt_pct(extra['data_quality']['freshness_score_pct'])}",
            "",
            "## Learning Status",
            "",
            f"- Assets With Learning: {extra['learning_status']['assets_with_learning']}",
            f"- Total Learning Updates: {extra['learning_status']['total_learning_updates']}",
            f"- Avg Memory Edge Delta: {fmt_num(extra['learning_status']['avg_memory_edge_delta'],4)}",
            f"- Avg Wait Seconds Delta: {fmt_num(extra['learning_status']['avg_wait_seconds_delta'],1)}",
            f"- Avg Risk Multiplier Delta: {fmt_num(extra['learning_status']['avg_risk_multiplier_delta'],4)}",
            f"- Latest Learning Update: {extra['learning_status']['latest_learning_update'] or 'N/A'}",
            "",
            "## AI Brain Activity",
            "",
            f"- Events Analyzed: {extra['brain_activity']['events_analyzed']}",
            f"- Candidate Decisions: {extra['brain_activity']['candidate_decisions']}",
            f"- Selected Decisions: {extra['brain_activity']['selected_decisions']}",
            f"- Executions: {extra['brain_activity']['executions']}",
            f"- Reason Paths Evaluated: {extra['brain_activity']['reason_paths_evaluated']}",
            f"- Asset Ranking Paths: {extra['brain_activity']['asset_ranking_paths']}",
            f"- Macro Regime Snapshots: {extra['brain_activity']['macro_regime_snapshots']}",
            f"- Exit Reviews: {extra['brain_activity']['exit_reviews']}",
            "",
            "## Risk Environment",
            "",
            f"- Risk Environment: {extra['risk_environment']['risk_environment']}",
            f"- Risk Score: {fmt_num(extra['risk_environment']['risk_score'])}/100",
            f"- Dominant Regime: {extra['risk_environment']['dominant_regime'] or 'N/A'}",
            f"- Top Macro Regimes: {extra['risk_environment']['top_macro_regimes']}",
            "",
            "## Version And Model Health",
            "",
        ]
    )
    for row in extra["version_health"]["model_health"]:
        lines.append(f"- {row['asset']}: status={row['status']} | health={fmt_num(row['health_score'])}/100 | adapter={row['adapter']} | source=`{row['source']}`")
    latest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    state = load_state()
    runtime = summarize_runtime(state)
    reports = latest_cycle_reports(state)
    latest_payloads = [json.loads(p.read_text(encoding="utf-8")) for p in reports]
    candidates, selected, executions, telegram_rows = flatten_latest_cycle(reports)
    historical = load_historical_db()
    asset_rows = summarize_assets(candidates, selected, executions, telegram_rows, historical)
    log_summary = parse_runtime_log()
    decision_distribution = summarize_decision_distribution(candidates, selected)
    decision_reasons = summarize_decision_reasons(candidates, selected)
    data_quality = summarize_data_quality(state, reports, candidates, selected, executions)
    learning_status = summarize_learning_status(asset_rows)
    brain_activity = summarize_brain_activity(candidates, selected, executions, latest_payloads)
    risk_environment = summarize_risk_environment(latest_payloads)
    version_health = summarize_version_and_health(asset_rows, executions, candidates, data_quality, runtime, log_summary)
    continuous_runtime_text = "N/A"
    if log_summary.get("first_cycle_start"):
        end_dt = log_summary.get("last_cycle_finish") or datetime.now(timezone.utc)
        continuous_runtime_text = fmt_duration((end_dt - log_summary["first_cycle_start"]).total_seconds())
    extra = {
        "log_summary": log_summary,
        "decision_distribution": decision_distribution,
        "decision_reasons": decision_reasons,
        "data_quality": data_quality,
        "learning_status": learning_status,
        "brain_activity": brain_activity,
        "risk_environment": risk_environment,
        "version_health": version_health,
        "continuous_runtime_text": continuous_runtime_text,
    }
    report_path = write_report(runtime, asset_rows, reports, extra)

    print("InsightBridge Financial Models KPI Report")
    print("=" * 60)
    print(f"base: {BASE}")
    print(f"runner_running: {runtime['runner_running']}")
    print(f"latest_cycle: {runtime['cycle_number']} | status={runtime['status']} | ok={runtime['ok_count']}/{runtime['event_count']}")
    print(f"latest_cycle_duration_seconds: {runtime['duration_seconds']}")
    print(f"continuous_runtime: {continuous_runtime_text}")
    print(f"system_availability: {fmt_pct(log_summary.get('system_availability_pct'))}")
    print(f"data_quality_score: {fmt_num(data_quality.get('data_quality_score'))}/100")
    print(f"risk_environment: {risk_environment['risk_environment']} | score={fmt_num(risk_environment.get('risk_score'))}/100 | dominant={risk_environment.get('dominant_regime')}")
    print(f"learning_status: assets={learning_status['assets_with_learning']} | updates={learning_status['total_learning_updates']} | latest={learning_status.get('latest_learning_update') or 'N/A'}")
    print(f"financial_ai_platform_score: {fmt_num(version_health['financial_ai_platform_score'])}/100")
    print("-" * 60)
    print("Five Financial Models")
    print("Asset | Selected Rate | Accepted Rate | Avg Confidence | Avg Wait | Hist Trades | Hist Avg PnL")
    for row in asset_rows:
        print(
            f"{row['asset']} | {fmt_pct(row.get('selected_rate_pct'))} | {fmt_pct(row.get('accepted_rate_pct'))} | "
            f"{fmt_pct(row.get('avg_execution_confidence_pct'))} | {fmt_num(row.get('avg_wait_seconds'),1)}s | "
            f"{row.get('historical_trades',0)} | {fmt_pct(row.get('historical_avg_pnl_pct'))}"
        )
        print(
            f"  reason={row.get('top_selected_reason') or row.get('top_candidate_reason') or 'N/A'} | "
            f"action={row.get('top_action') or 'N/A'} | learning_updates={row.get('learning_updates',0)}"
        )
    print("-" * 60)
    print(f"Saved report: {report_path}")
    print(f"Latest alias: {REPORTS_DIR / 'financial_model_kpi_report_latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
