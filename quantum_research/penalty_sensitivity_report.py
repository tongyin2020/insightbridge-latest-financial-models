#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_CSV = PROJECT_BASE / "reports" / "quantum_research" / "penalty_results.csv"
DEFAULT_OUTPUT = PROJECT_BASE / "reports" / "quantum_research" / "penalty_sensitivity_report.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build markdown report from penalty tuning CSV.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv).expanduser()
    output_md = Path(args.output_md).expanduser()
    output_md.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    winners = Counter(row["best_subset"] for row in rows)
    by_corr = defaultdict(Counter)
    by_size = defaultdict(Counter)
    for row in rows:
        by_corr[row["lambda_corr"]][row["best_subset"]] += 1
        by_size[row["lambda_size"]][row["best_subset"]] += 1

    top_subset, top_count = winners.most_common(1)[0]
    total = len(rows)
    lines = [
        "# EventAlpha Penalty Sensitivity Report",
        "",
        f"- source_csv: `{csv_path}`",
        f"- total_grid_rows: {total}",
        f"- unique_winner_count: {len(winners)}",
        f"- robust_preferred_subset: `{top_subset}`",
        f"- robust_preferred_share: {top_count / total:.1%}",
        "",
        "## Winner Frequency",
        "",
    ]
    for subset, count in winners.most_common():
        lines.append(f"- `{subset}` -> {count} / {total} ({count/total:.1%})")

    lines.extend(["", "## Correlation Penalty Regimes", ""])
    for lambda_corr, counter in sorted(by_corr.items()):
        subset, count = counter.most_common(1)[0]
        lines.append(f"- `lambda_corr={lambda_corr}` -> `{subset}` wins {count} times")

    lines.extend(["", "## Size Penalty Regimes", ""])
    for lambda_size, counter in sorted(by_size.items()):
        subset, count = counter.most_common(1)[0]
        lines.append(f"- `lambda_size={lambda_size}` -> `{subset}` wins {count} times")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The stable winner is the subset that dominates across the widest penalty surface, not just at one tuned point.",
            "If one subset wins more than 60% of the grid, it can be treated as a robust preferred allocation for the current EventAlpha case pack.",
        ]
    )
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Penalty sensitivity report built")
    print("=" * 60)
    print(f"report: {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
