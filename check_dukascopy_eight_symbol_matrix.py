#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
SOURCE_JAR = Path("/Users/tongyin/JForex4/libs/demo/4.8.15/jforex-api-4.8.13-sources.jar")
REPORT_DIR = BASE / "reports" / "broker_diagnostics"
REPORT_JSON = REPORT_DIR / "dukascopy_eight_symbol_matrix_latest.json"
REPORT_MD = REPORT_DIR / "dukascopy_eight_symbol_matrix_latest.md"


@dataclass
class MappingRow:
    logical_symbol: str
    requested_asset: str
    dukascopy_mode: str
    dukascopy_candidate: str | None
    api_candidate_exists: bool
    recommendation: str
    notes: str


TARGET_MATRIX = [
    MappingRow("EURUSD", "Spot FX", "direct", "EUR/USD", False, "", "Dukascopy strong fit."),
    MappingRow("USDJPY", "Spot FX", "direct", "USD/JPY", False, "", "Dukascopy strong fit."),
    MappingRow("BTC", "Crypto spot/CFD", "direct", "BTC/USD", False, "", "Depends on demo-market availability and permissions."),
    MappingRow("MES", "Micro S&P 500 future", "proxy", "USA500.IDX/USD", False, "", "Proxy only; index CFD, not CME micro future."),
    MappingRow("MNQ", "Micro Nasdaq future", "proxy", "USATECH.IDX/USD", False, "", "Proxy only; index CFD, not CME micro future."),
    MappingRow("ZT", "2Y Treasury future", "unsupported", None, False, "", "No clean Dukascopy treasury future mapping in public API."),
    MappingRow("ZN", "10Y Treasury future", "unsupported", None, False, "", "No clean Dukascopy treasury future mapping in public API."),
    MappingRow("SR3", "3M SOFR future", "unsupported", None, False, "", "No clean Dukascopy short-rate future mapping in public API."),
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_instrument_strings() -> set[str]:
    if not SOURCE_JAR.exists():
        return set()
    with ZipFile(SOURCE_JAR) as zf:
        source = zf.read("com/dukascopy/api/Instrument.java").decode("utf-8", errors="ignore")

    out: set[str] = set()
    for primary, secondary in re.findall(r'createForexInstrument\("([^"]+)",\s*"([^"]+)"', source):
        out.add(f"{primary}/{secondary}".upper())
    for primary, secondary in re.findall(r'createCfdInstrument\("([^"]+)",\s*"([^"]+)"', source):
        out.add(f"{primary}/{secondary}".upper())
    for primary, secondary in re.findall(r'createPredefinedInstrument\(Type\.(?:CFD|METAL),\s*"([^"]+)",\s*"([^"]+)"', source):
        out.add(f"{primary}/{secondary}".upper())
    return out


def build_rows() -> list[MappingRow]:
    known = load_instrument_strings()
    rows: list[MappingRow] = []
    for row in TARGET_MATRIX:
        exists = bool(row.dukascopy_candidate and row.dukascopy_candidate.upper() in known)
        recommendation = "cannot_test_here"
        if row.dukascopy_mode == "direct" and exists:
            recommendation = "can_probe_now"
        elif row.dukascopy_mode == "proxy" and exists:
            recommendation = "can_probe_as_proxy_only"
        elif row.dukascopy_mode == "unsupported":
            recommendation = "do_not_route_to_dukascopy"
        elif row.dukascopy_candidate and not exists:
            recommendation = "candidate_missing_from_api"

        rows.append(
            MappingRow(
                logical_symbol=row.logical_symbol,
                requested_asset=row.requested_asset,
                dukascopy_mode=row.dukascopy_mode,
                dukascopy_candidate=row.dukascopy_candidate,
                api_candidate_exists=exists,
                recommendation=recommendation,
                notes=row.notes,
            )
        )
    return rows


def write_reports(rows: list[MappingRow]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": now_utc(),
        "project": str(BASE),
        "source_jar": str(SOURCE_JAR),
        "probe_csv_for_jforex": "EURUSD,USDJPY,BTC,MES,MNQ,ZT,ZN,SR3",
        "resolved_probe_targets": [
            row.dukascopy_candidate for row in rows
            if row.recommendation in {"can_probe_now", "can_probe_as_proxy_only"} and row.dukascopy_candidate
        ],
        "rows": [asdict(r) for r in rows],
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Dukascopy Eight-Symbol Compatibility Matrix",
        "",
        f"- generated_at: {payload['generated_at']}",
        f"- project: `{BASE}`",
        f"- source_jar: `{SOURCE_JAR}`",
        f"- probe_csv_for_jforex: `{payload['probe_csv_for_jforex']}`",
        f"- resolved_probe_targets: `{', '.join(payload['resolved_probe_targets'])}`",
        "",
        "| Logical Symbol | Requested Asset | Mode | Dukascopy Candidate | API Exists | Recommendation |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.logical_symbol} | {row.requested_asset} | {row.dukascopy_mode} | "
            f"{row.dukascopy_candidate or '-'} | {'yes' if row.api_candidate_exists else 'no'} | {row.recommendation} |"
        )
    lines.extend([
        "",
        "## Notes",
        "",
    ])
    for row in rows:
        lines.append(f"- `{row.logical_symbol}`: {row.notes}")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows = build_rows()
    write_reports(rows)

    print("InsightBridge Dukascopy Eight-Symbol Matrix")
    print("=" * 60)
    print(f"project: {BASE}")
    print(f"source_jar: {SOURCE_JAR}")
    print(f"generated_at: {now_utc()}")
    print(f"probe_csv_for_jforex: EURUSD,USDJPY,BTC,MES,MNQ,ZT,ZN,SR3")
    print("-" * 60)
    for row in rows:
        print(f"[{row.logical_symbol}] {row.recommendation}")
        print(f"  requested_asset: {row.requested_asset}")
        print(f"  mode: {row.dukascopy_mode}")
        print(f"  dukascopy_candidate: {row.dukascopy_candidate}")
        print(f"  api_candidate_exists: {row.api_candidate_exists}")
        print(f"  notes: {row.notes}")
        print("-" * 60)
    print(f"saved_json: {REPORT_JSON}")
    print(f"saved_md: {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
