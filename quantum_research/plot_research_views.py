#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from statistics import mean


PROJECT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_CSV = PROJECT_BASE / "reports" / "quantum_research" / "dashboard_runs.csv"
DEFAULT_OUTDIR = PROJECT_BASE / "reports" / "quantum_research" / "dashboard_charts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate HTML research views from quantum dashboard CSV.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def bar_svg(items: list[tuple[str, float]], width: int = 720, height: int = 220, color: str = "#2563eb") -> str:
    if not items:
        return "<p>No data.</p>"
    max_value = max(value for _, value in items) or 1.0
    bar_width = max(40, int((width - 80) / len(items)))
    baseline = height - 30
    pieces = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    pieces.append(f'<line x1="20" y1="{baseline}" x2="{width-20}" y2="{baseline}" stroke="#94a3b8" stroke-width="1"/>')
    for idx, (label, value) in enumerate(items):
        x = 40 + idx * bar_width
        bar_h = 0 if max_value == 0 else int((value / max_value) * (height - 80))
        y = baseline - bar_h
        pieces.append(f'<rect x="{x}" y="{y}" width="{bar_width-16}" height="{bar_h}" rx="8" fill="{color}"/>')
        pieces.append(f'<text x="{x + (bar_width-16)/2}" y="{baseline + 16}" text-anchor="middle" font-size="11" fill="#e2e8f0">{html.escape(label)}</text>')
        pieces.append(f'<text x="{x + (bar_width-16)/2}" y="{max(18, y-6)}" text-anchor="middle" font-size="11" fill="#cbd5e1">{value:.3f}</text>')
    pieces.append("</svg>")
    return "".join(pieces)


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv).expanduser()
    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    rows = load_rows(csv_path)

    by_problem: dict[str, list[dict[str, str]]] = {}
    by_mode: dict[str, list[dict[str, str]]] = {}
    exact_match = 0
    deltas = []
    for row in rows:
        by_problem.setdefault(row["problem"], []).append(row)
        by_mode.setdefault(row["run_type"], []).append(row)
        delta = float(row["delta_vs_exact"])
        deltas.append(delta)
        if abs(delta) < 1e-9:
            exact_match += 1

    problem_counts = [(problem, float(len(items))) for problem, items in sorted(by_problem.items())]
    mode_counts = [(mode, float(len(items))) for mode, items in sorted(by_mode.items())]
    avg_delta_problem = [
        (problem, mean(float(item["delta_vs_exact"]) for item in items))
        for problem, items in sorted(by_problem.items())
    ]

    summary = {
        "row_count": len(rows),
        "exact_match_rate": 0.0 if not rows else round(exact_match / len(rows), 4),
        "avg_delta_all": 0.0 if not deltas else round(mean(deltas), 6),
        "best_delta": 0.0 if not deltas else round(max(deltas), 6),
        "worst_delta": 0.0 if not deltas else round(min(deltas), 6),
    }
    (outdir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>EventAlpha Quantum Research Dashboard</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 18px; padding: 18px; }}
    h1, h2 {{ margin: 0 0 14px; }}
    .muted {{ color: #94a3b8; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #334155; text-align: left; padding: 8px 4px; }}
    .section {{ margin-top: 28px; }}
  </style>
</head>
<body>
  <h1>EventAlpha Quantum Research Dashboard</h1>
  <p class="muted">Generated from {html.escape(str(csv_path))}</p>
  <div class="grid">
    <div class="card"><div class="muted">Total Runs</div><div style="font-size:32px;font-weight:700;">{summary['row_count']}</div></div>
    <div class="card"><div class="muted">Exact Match Rate</div><div style="font-size:32px;font-weight:700;">{summary['exact_match_rate']:.1%}</div></div>
    <div class="card"><div class="muted">Average Delta</div><div style="font-size:32px;font-weight:700;">{summary['avg_delta_all']:.4f}</div></div>
    <div class="card"><div class="muted">Worst Delta</div><div style="font-size:32px;font-weight:700;">{summary['worst_delta']:.4f}</div></div>
  </div>
  <div class="section card">
    <h2>Runs By Problem</h2>
    {bar_svg(problem_counts, color="#10b981")}
  </div>
  <div class="section card">
    <h2>Runs By Mode</h2>
    {bar_svg(mode_counts, color="#f59e0b")}
  </div>
  <div class="section card">
    <h2>Average Delta By Problem</h2>
    {bar_svg(avg_delta_problem, color="#ef4444")}
  </div>
  <div class="section card">
    <h2>Problem Table</h2>
    <table>
      <thead><tr><th>Problem</th><th>Runs</th><th>Average Delta</th><th>Exact Match Rate</th></tr></thead>
      <tbody>
        {''.join(f"<tr><td>{html.escape(problem)}</td><td>{len(items)}</td><td>{mean(float(item['delta_vs_exact']) for item in items):.6f}</td><td>{sum(1 for item in items if abs(float(item['delta_vs_exact'])) < 1e-9)/len(items):.1%}</td></tr>" for problem, items in sorted(by_problem.items()))}
      </tbody>
    </table>
  </div>
</body>
</html>
"""
    (outdir / "index.html").write_text(html_doc, encoding="utf-8")
    print("Quantum research views generated")
    print("=" * 60)
    print(f"html: {outdir / 'index.html'}")
    print(f"summary: {outdir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
