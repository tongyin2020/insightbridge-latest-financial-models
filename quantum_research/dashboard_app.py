#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
import socketserver
import subprocess
import sys
from pathlib import Path


PROJECT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_CSV = PROJECT_BASE / "reports" / "quantum_research" / "dashboard_runs.csv"
DEFAULT_OUTDIR = PROJECT_BASE / "reports" / "quantum_research" / "dashboard_charts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the EventAlpha quantum dashboard locally.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--rebuild", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv).expanduser()
    outdir = Path(args.outdir).expanduser()
    if args.rebuild:
        subprocess.check_call(
            [
                sys.executable,
                str(PROJECT_BASE / "quantum_research" / "plot_research_views.py"),
                "--csv",
                str(csv_path),
                "--outdir",
                str(outdir),
            ]
        )
    outdir.mkdir(parents=True, exist_ok=True)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("127.0.0.1", args.port), lambda *a, **kw: handler(*a, directory=str(outdir), **kw)) as httpd:
        print("EventAlpha Quantum Dashboard App")
        print("=" * 60)
        print(f"serving: {outdir}")
        print(f"url: http://127.0.0.1:{args.port}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
