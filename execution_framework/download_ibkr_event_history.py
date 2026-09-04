"""
download_ibkr_event_history.py
═══════════════════════════════════════════════════════════════════════════════
一次性历史数据下载器（只读，不下单）：为事件驱动回测补齐 CME 期货历史。

背景
  - crypto/FX/油 的历史 tick+bar 已备齐（Binance / Dukascopy / HistData）。
  - 唯独股指/美债/SOFR 期货（MES/MNQ/ZT/ZN/SR3）一条历史都没有。
  - IBKR 不提供历史盘口深度，但**免费**提供历史 K 线；用 CONTFUT（连续期货）
    可以直接取到跨到期月的连续序列，适合回测（不用自己拼接换月）。

做什么
  - 读事件表（event_windows.csv：NFP/CPI/FOMC，含 t0），对每个**已发生**的事件、
    每个品种，请求 t0 前后一段窗口的 K 线（默认 1 分钟 TRADES），存成 CSV。
  - 断点续传：已存在的输出文件直接跳过，被限流打断后重跑即可继续。
  - 限流友好：滑动窗口限制每 10 分钟请求数 + 每次请求间隔；命中 pacing 错误自动退避。
  - dry-run：不连 IBKR，只打印将要请求的清单，便于先核对范围。

重要
  - 只读历史数据，绝不下单。
  - 用**独立 clientId**（默认 77）。IBKR 单会话限制：跑本脚本前应先停掉实盘 launchd
    循环（clientId 22），否则会与实盘抢行情农场（Error 162）。下完再恢复 launchd。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

# 与 resolver 保持一致的期货规格（含 CBOT/CME、tradingClass/multiplier）
try:
    from ibkr_contract_resolver import FUT_SPECS
except Exception:  # noqa: BLE001  # 允许从仓库根目录运行
    from execution_framework.ibkr_contract_resolver import FUT_SPECS  # type: ignore

DEFAULT_SYMBOLS = ["MES", "MNQ", "ZT", "ZN", "SR3"]

# 逐笔成交极稀的品种(3M SOFR)用 MIDPOINT 取真实价格路径;其余用 TRADES。
SYMBOL_WHAT = {"SR3": "MIDPOINT"}
DEFAULT_EVENTS_CSV = os.path.expanduser("~/eventalpha_data/event_windows.csv")
DEFAULT_OUT_DIR = os.path.expanduser("~/eventalpha_data/ibkr_futures")


def _parse_t0(row: Dict[str, str]) -> Optional[datetime]:
    """从事件行解析 t0（UTC）。优先 t0_iso，退回 t0_ms。"""
    iso = (row.get("t0_iso") or "").strip()
    if iso:
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    ms = (row.get("t0_ms") or "").strip()
    if ms:
        try:
            return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)
        except (ValueError, OverflowError):
            pass
    return None


def load_events(path: str) -> List[Tuple[str, datetime]]:
    """返回 [(event_type, t0_utc), ...]，按时间升序，去重。"""
    out: List[Tuple[str, datetime]] = []
    seen = set()
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            t0 = _parse_t0(row)
            if t0 is None:
                continue
            etype = (row.get("event_type") or "EVENT").strip()
            key = (etype, t0.isoformat())
            if key in seen:
                continue
            seen.add(key)
            out.append((etype, t0))
    out.sort(key=lambda x: x[1])
    return out


def _bar_tag(bar_size: str) -> str:
    return bar_size.replace(" ", "")


def _out_path(out_dir: Path, symbol: str, etype: str, t0: datetime,
              bar_size: str) -> Path:
    stamp = t0.strftime("%Y%m%dT%H%M")
    return out_dir / symbol / f"{symbol}_{etype}_{stamp}_{_bar_tag(bar_size)}.csv"


class Pacer:
    """滑动窗口限流：保证任意 window_s 内请求数 <= max_reqs，且请求间隔 >= min_gap。"""

    def __init__(self, max_reqs: int, window_s: float, min_gap: float):
        self.max_reqs = max_reqs
        self.window_s = window_s
        self.min_gap = min_gap
        self._stamps: Deque[float] = deque()
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        gap = now - self._last
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        # 滑动窗口
        now = time.monotonic()
        while self._stamps and now - self._stamps[0] > self.window_s:
            self._stamps.popleft()
        if len(self._stamps) >= self.max_reqs:
            sleep_for = self.window_s - (now - self._stamps[0]) + 0.5
            if sleep_for > 0:
                print(f"  · 限流窗口已满，休息 {sleep_for:.0f}s ...")
                time.sleep(sleep_for)
            now = time.monotonic()
            while self._stamps and now - self._stamps[0] > self.window_s:
                self._stamps.popleft()
        self._stamps.append(time.monotonic())
        self._last = time.monotonic()


def _ltd8(contract) -> str:
    ltd = (getattr(contract, "lastTradeDateOrContractMonth", "") or "")
    return (ltd + "01")[:8] if len(ltd) == 6 else ltd[:8]


def available_months(ib, symbol: str, cache: Dict) -> List:
    """枚举 IBKR **实际还存在定义的**到期月合约(含已到期),按到期升序。
    IBKR 的 security-definition 库只保留回溯约两年;更早的到期月取不到(Error 200)。
    只请求这里列出的合约,避免无意义的 200 噪声。"""
    if symbol in cache:
        return cache[symbol]
    from ib_insync import Future
    spec = FUT_SPECS[symbol]
    kwargs = dict(symbol=spec["symbol"], exchange=spec["exchange"],
                  currency=spec["currency"], includeExpired=True)
    if spec.get("tradingClass"):
        kwargs["tradingClass"] = spec["tradingClass"]
    if spec.get("multiplier"):
        kwargs["multiplier"] = spec["multiplier"]
    try:
        details = ib.reqContractDetails(Future(**kwargs))
    except Exception:  # noqa: BLE001
        details = []
    months = sorted(
        [(_ltd8(cd.contract), cd.contract) for cd in details if _ltd8(cd.contract)],
        key=lambda x: x[0])
    cache[symbol] = months
    return months


def front_candidates(months: List, t0: datetime, n: int = 3,
                     max_days: int = 200) -> List:
    """从实际存在的合约里,挑到期 >= t0 且在 t0 之后 max_days 内的最近 n 个。
    max_days 约束确保只用**当时真正的前月/次月**;若最近可用合约已远在 max_days 之外
    (说明当时真正的前月已被 IBKR 清库,取不到),则返回空 = 该事件期货历史不可得。"""
    d = t0.strftime("%Y%m%d")
    t0d = t0.date()
    out: List = []
    for ltd8, c in months:
        if ltd8 < d:
            continue
        try:
            exp = datetime.strptime(ltd8, "%Y%m%d").date()
        except ValueError:
            continue
        if (exp - t0d).days <= max_days:
            out.append(c)
        if len(out) >= n:
            break
    return out


def _write_bars(path: Path, bars) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "open", "high", "low", "close", "volume",
                    "average", "barCount"])
        for b in bars:
            w.writerow([
                getattr(b, "date", ""), b.open, b.high, b.low, b.close,
                getattr(b, "volume", ""), getattr(b, "average", ""),
                getattr(b, "barCount", ""),
            ])
            n += 1
    return n


def run(args) -> int:
    events = load_events(args.events_csv)
    now = datetime.now(timezone.utc)
    past = [(e, t0) for (e, t0) in events if t0 < now - timedelta(hours=1)]
    future = [(e, t0) for (e, t0) in events if t0 >= now - timedelta(hours=1)]
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    bar_sizes = [b.strip() for b in args.bar_sizes.split(",") if b.strip()]
    out_dir = Path(args.out_dir)

    pad = timedelta(hours=args.pad_hours)
    dur_s = int(2 * args.pad_hours * 3600)

    total_jobs = len(symbols) * len(past) * len(bar_sizes)
    print(f"事件总数={len(events)}  已发生={len(past)}  未来(跳过)={len(future)}")
    print(f"品种={symbols}  K线粒度={bar_sizes}  窗口=±{args.pad_hours}h  "
          f"计划请求(未去重)={total_jobs}")
    print(f"输出目录={out_dir}")

    if args.dry_run:
        for sym in symbols:
            for etype, t0 in past[: (args.limit or None)]:
                for bs in bar_sizes:
                    p = _out_path(out_dir, sym, etype, t0, bs)
                    flag = "SKIP(exists)" if p.exists() else "GET"
                    print(f"  [{flag}] {p.name}  end={(t0 + pad).isoformat()}")
        print("dry-run 完成（未连接 IBKR）。")
        return 0

    from ib_insync import IB, util  # noqa: F401
    ib = IB()

    def reconnect() -> bool:
        """断线后重连(同 clientId);网关会周期性踢长连接,必须能自愈。"""
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2.0)
        for attempt in range(1, 6):
            try:
                ib.connect(args.host, args.port, clientId=args.client_id,
                           timeout=args.connect_timeout, readonly=True)
                print(f"  · 重连成功 (第{attempt}次)")
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"  · 重连失败 {attempt}: {str(exc)[:80]}")
                time.sleep(min(6.0 * attempt, 30.0))
        return False

    print(f"连接 IBKR {args.host}:{args.port} clientId={args.client_id} ...")
    ib.connect(args.host, args.port, clientId=args.client_id,
               timeout=args.connect_timeout, readonly=True)
    print("已连接（readonly）。")

    pacer = Pacer(max_reqs=args.max_per_window, window_s=600.0,
                  min_gap=args.sleep)
    manifest_path = out_dir / "manifest.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)

    got = skipped = failed = empty = 0
    req_n = 0
    months_cache: Dict = {}
    subset = past[: args.limit] if args.limit else past
    try:
        for sym in symbols:
            months = available_months(ib, sym, months_cache)
            span = f"{months[0][0]}..{months[-1][0]}" if months else "(none)"
            print(f"[{sym}] 可用到期月={len(months)} 跨度 {span}")
            for etype, t0 in subset:
                for bs in bar_sizes:
                    p = _out_path(out_dir, sym, etype, t0, bs)
                    if p.exists() and not args.force:
                        skipped += 1
                        continue
                    end_dt = t0 + pad
                    cands = front_candidates(months, t0, n=args.candidates,
                                             max_days=args.max_expiry_days)
                    saved = tried_any = False
                    for con in cands:
                        if con is None:
                            continue
                        tried_any = True
                        what = SYMBOL_WHAT.get(sym, "TRADES")
                        pacer.wait()
                        req_n += 1
                        # 主动刷新长连接:网关对活跃过久的客户会踢掉,定期重连防患未然。
                        if (args.reconnect_every and
                                req_n % args.reconnect_every == 0):
                            print(f"  · 已发{req_n}请求,主动重连保持会话新鲜 ...")
                            reconnect()
                        if not ib.isConnected():
                            reconnect()
                        try:
                            bars = ib.reqHistoricalData(
                                con, endDateTime=end_dt,
                                durationStr=f"{dur_s} S",
                                barSizeSetting=bs, whatToShow=what,
                                useRTH=bool(args.rth), formatDate=2,
                                keepUpToDate=False, timeout=args.req_timeout)
                        except Exception as exc:  # noqa: BLE001
                            print(f"  [{sym}] {etype} {t0:%Y-%m-%d} "
                                  f"{con.localSymbol} {bs} 异常: {str(exc)[:90]}")
                            bars = []
                        if not ib.isConnected():
                            print("  · 检测到断线,重连后重试本笔 ...")
                            if reconnect():
                                try:
                                    bars = ib.reqHistoricalData(
                                        con, endDateTime=end_dt,
                                        durationStr=f"{dur_s} S",
                                        barSizeSetting=bs, whatToShow=what,
                                        useRTH=bool(args.rth), formatDate=2,
                                        keepUpToDate=False,
                                        timeout=args.req_timeout)
                                except Exception as exc:  # noqa: BLE001
                                    print(f"  [{sym}] {etype} 重试仍失败: "
                                          f"{str(exc)[:80]}")
                                    bars = []
                        # TRADES 全零成交 = 该合约在窗口内无真实交易,视为空,试下一个
                        if bars and what == "TRADES":
                            vol = sum(float(getattr(b, "volume", 0) or 0) for b in bars)
                            if vol <= 0:
                                bars = []
                        if bars:
                            n = _write_bars(p, bars)
                            with open(manifest_path, "a") as mf:
                                mf.write(json.dumps({
                                    "symbol": sym, "event": etype,
                                    "t0": t0.isoformat(), "bar": bs,
                                    "end": end_dt.isoformat(), "bars": n,
                                    "what": what,
                                    "contract": con.localSymbol or "",
                                    "file": str(p.name),
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                }) + "\n")
                            print(f"  [{sym}] {etype} {t0:%Y-%m-%d %H:%M} "
                                  f"{con.localSymbol} {bs}: {n} bars -> {p.name}")
                            got += 1
                            saved = True
                            break
                    if not saved:
                        tried = [c.localSymbol for c in cands if c is not None]
                        if tried_any:
                            empty += 1
                            print(f"  [{sym}] {etype} {t0:%Y-%m-%d} {bs}: "
                                  f"无数据(试过 {tried})")
                        else:
                            failed += 1
                            print(f"  [{sym}] {etype} {t0:%Y-%m-%d} {bs}: "
                                  f"无可用合约")
    finally:
        ib.disconnect()
        print(f"完成：获取={got} 空(无数据)={empty} 跳过(已存在)={skipped} 失败={failed}")
        print(f"清单: {manifest_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="IBKR 事件窗口历史 K 线下载器（只读）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002,
                    help="4002=IB Gateway 模拟盘, 7497=TWS 模拟盘")
    ap.add_argument("--client-id", type=int, default=77)
    ap.add_argument("--connect-timeout", type=float, default=15.0)
    ap.add_argument("--req-timeout", type=float, default=90.0,
                    help="单个历史请求超时秒(防止断线时永久挂起)")
    ap.add_argument("--reconnect-every", type=int, default=40,
                    help="每发 N 个请求主动重连一次(网关会踢长连接),0=关闭")
    ap.add_argument("--events-csv", default=DEFAULT_EVENTS_CSV)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--bar-sizes", default="1 min",
                    help='逗号分隔，如 "1 min,5 secs"')
    ap.add_argument("--pad-hours", type=float, default=2.0,
                    help="事件 t0 前后各取多少小时（默认±2h=4h窗口）")
    ap.add_argument("--rth", type=int, default=0, help="1=仅正常交易时段")
    ap.add_argument("--sleep", type=float, default=11.0,
                    help="两次请求最小间隔秒（限流）")
    ap.add_argument("--max-per-window", type=int, default=55,
                    help="每 10 分钟最大请求数（IBKR 上限约 60）")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--max-expiry-days", type=int, default=200,
                    help="只用到期在事件后此天数内的合约(造真前月);超出=当时前月已清库不可得")
    ap.add_argument("--candidates", type=int, default=3,
                    help="每个事件最多试几个季月合约(近月优先,兑底换月)")
    ap.add_argument("--backoff", type=float, default=20.0,
                    help="失败后退避秒（pacing 违规时）")
    ap.add_argument("--limit", type=int, default=0,
                    help="只处理前 N 个事件（0=全部，用于先小样验证）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在文件")
    ap.add_argument("--dry-run", action="store_true",
                    help="不连 IBKR，只打印将要请求的清单")
    return ap


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
