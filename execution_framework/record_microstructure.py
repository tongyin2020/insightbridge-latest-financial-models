"""Step 2 · Phase A — standalone microstructure recorder.

Purpose
═══════
Capture real Level-2 depth + bar-seeded tape and log what the Step-1 gates WOULD
say (OBI fakeout / CVD top divergence / near-side liquidity crash), *without*
going through the full continuous trading pipeline.

Why a separate tool
───────────────────
``run_tws_continuous.py`` runs the whole trading pipeline: it reconciles broker
vs. local positions and **halts the whole loop on any desync** (a safety feature).
When you already hold a paper position from the 24/7 launchd loop, a second manual
instance sees that position, halts, and never reaches the per-symbol scan — so the
microstructure shadow never records a line. This recorder does *only* the data
capture: connect → resolve → ``reqMktDepth`` + 1-min bars → run Step-1 gates in
observe-only mode → append JSONL. No reconciliation, no halting, no orders.

Safety
──────
* **Never places, modifies, or cancels any order.** Read-only market data.
* Uses ``MicrostructureShadow`` (observe-only) for the verdict + JSONL logging.
* Every broker call degrades to ``None``/empty on error; a single bad symbol or a
  disconnect never aborts the whole run.
* Use a **unique** ``--client-id`` (the launchd realtime loop holds 22).

Example
───────
    EVENTALPHA_MICROSTRUCTURE_SHADOW=1 python3 \\
        execution_framework/record_microstructure.py \\
        --client-id 44 --symbols EURUSD,USDJPY,BTC --interval 60 --minutes 20

The core loop (:func:`record_once`) is duck-typed against ib_insync so it is unit
testable with a fake ``ib`` and no TWS.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

BASE = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BASE / "reports" / "runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(BASE / "execution_framework"))
sys.path.insert(0, str(BASE))

from depth_collector import DepthCollector           # noqa: E402
from microstructure_shadow import MicrostructureShadow  # noqa: E402


def _bars_to_df(bars: Any):
    import pandas as pd
    return pd.DataFrame([{"open": b.open, "high": b.high, "low": b.low,
                          "close": b.close, "volume": getattr(b, "volume", 0) or 0}
                         for b in bars])


def _historical_what_to_show(resolved: Any) -> str:
    sec_type = getattr(resolved, "sec_type", "")
    if sec_type == "CASH":
        return "MIDPOINT"
    if sec_type == "CRYPTO":
        return "AGGTRADES"
    return "TRADES"


def _fetch_tape_df(ib: Any, resolved: Any):
    """Best-effort 1-min bar pull to seed the CVD tape. Returns df or None."""
    try:
        bars = ib.reqHistoricalData(
            resolved.raw, endDateTime="", durationStr="2 D",
            barSizeSetting="1 min", whatToShow=_historical_what_to_show(resolved),
            useRTH=False, formatDate=1)
        df = _bars_to_df(bars)
        if len(df) < 2:
            return None
        return df
    except Exception:                       # noqa: BLE001
        return None


def _direction_from_df(df: Any) -> str:
    try:
        closes = df["close"].tolist()
        ref = closes[-min(len(closes), 10)]
        return "long" if closes[-1] >= ref else "short"
    except Exception:                       # noqa: BLE001
        return "long"


def record_once(ib: Any, resolver: Any, collector: DepthCollector,
                shadow: MicrostructureShadow, symbols: List[str]) -> int:
    """One capture pass over all symbols. Returns number of JSONL lines written.

    Read-only: resolves each contract, seeds the tape from 1-min bars, pulls
    Level-2 depth, and records the observe-only verdict. Any per-symbol error is
    isolated so one bad symbol never aborts the pass."""
    written = 0
    for sym in symbols:
        try:
            rc = None
            get_cached = getattr(resolver, "get_cached", None)
            if get_cached is not None:
                rc = get_cached(sym)
            if rc is None or not getattr(rc, "is_locked", False):
                rc = resolver.resolve(sym, refresh=True)
            if rc is None or not getattr(rc, "is_locked", False):
                print(f"  [{sym}] 合约未锁定，跳过")
                continue

            df = _fetch_tape_df(ib, rc)
            if df is not None:
                collector.update_tape_from_df(sym, df)
            direction = _direction_from_df(df) if df is not None else "long"

            bid_sizes, ask_sizes = collector.fetch_depth(ib, rc.raw, sym)
            raw = collector.raw_for_exit(sym)
            rec = shadow.observe(
                sym, direction, bid_sizes, ask_sizes,
                recent_prices=raw["recent_prices"],
                recent_volumes=raw["recent_volumes"],
                near_side_size_series=raw["near_side_size_series"],
                tape_source=raw["tape_source"])
            if rec is not None:
                written += 1
                print(f"  [{sym}] obi={rec['obi']} "
                      f"n_bid={rec['n_bid_levels']} n_ask={rec['n_ask_levels']} "
                      f"n_tape={rec['n_tape']} tape={rec['tape_source']} dir={direction}")
            else:
                print(f"  [{sym}] 影子未记录（可能未开启或缺数据）")
        except Exception as exc:            # noqa: BLE001
            print(f"  [{sym}] 记录异常: {exc}")
    return written


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Step 2 · Phase A microstructure recorder (observe-only, read-only)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002,
                   help="4002=IB Gateway paper, 7497=TWS paper")
    p.add_argument("--client-id", type=int, default=44,
                   help="必须与 launchd 实盘循环(22)不同")
    p.add_argument("--symbols", default="EURUSD,USDJPY,BTC",
                   help="逗号分隔；免费深度: FX/WTI/加密")
    p.add_argument("--interval", type=float, default=60.0,
                   help="每轮采集间隔秒")
    p.add_argument("--depth-wait", type=float, default=4.0,
                   help="每个品种等订单簿异步填充的最长秒数（填满即提前返回）")
    p.add_argument("--minutes", type=float, default=20.0,
                   help="总运行分钟数（到时自动退出）")
    p.add_argument("--log-path",
                   default=str(RUNTIME_DIR / "microstructure_shadow.log"))
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

    shadow = MicrostructureShadow(log_path=args.log_path)
    if not shadow.ms_ok:
        print("⚠️ Step-1 微结构原语导入失败，无法记录。请检查 eventalpha_core。")
        return 2
    if not shadow.enabled:
        print("影子未开启：请设置环境变量 EVENTALPHA_MICROSTRUCTURE_SHADOW=1 再运行。")
        return 3
    print(f"microstructure 影子记录: 已开启 -> {args.log_path}")

    from ibkr_session import IBKRSession
    from ibkr_contract_resolver import IBKRContractResolver

    sess = IBKRSession(host=args.host, port=args.port, client_id=args.client_id)
    if not sess.connect():
        print("❌ 无法连接 IB Gateway/TWS。")
        return 4
    print(f"已连接 IBKR {args.host}:{args.port} (paper={sess.is_paper}) "
          f"clientId={args.client_id} — 只读采集，不下单")

    resolver = IBKRContractResolver(ib=sess.ib)
    collector = DepthCollector(depth_sleep=args.depth_wait)

    # Capture market-data / depth errors so we can tell *why* depth is empty
    # (permission vs. market-hours vs. not-supported) without scrolling the log.
    _INFO_CODES = {2104, 2106, 2158, 2107, 2119, 2100, 2150}
    depth_errs: List[str] = []

    def _on_err(reqId, code, msg, contract=None):  # noqa: ANN001
        try:
            if int(code) not in _INFO_CODES:
                depth_errs.append(f"Error {code}: {msg}")
        except Exception:                   # noqa: BLE001
            pass

    try:
        sess.ib.errorEvent += _on_err
    except Exception:                       # noqa: BLE001
        pass

    deadline = time.time() + args.minutes * 60.0
    round_no = 0
    total = 0
    try:
        while time.time() < deadline:
            round_no += 1
            print(f"[采集轮 {round_no}] {time.strftime('%H:%M:%S')}")
            depth_errs.clear()
            total += record_once(sess.ib, resolver, collector, shadow, symbols)
            if depth_errs:
                seen = set()
                for e in depth_errs:
                    if e not in seen:
                        seen.add(e)
                        print(f"    · IB: {e}")
            if time.time() >= deadline:
                break
            try:
                sess.ib.sleep(args.interval)
            except Exception:               # noqa: BLE001
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，停止采集。")
    finally:
        try:
            sess.disconnect()
        except Exception:                   # noqa: BLE001
            pass

    print(f"完成：共写入 {total} 行到 {args.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
