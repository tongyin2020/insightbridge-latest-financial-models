#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from eventalpha_hybrid import run_hybrid_eventalpha


def main() -> None:
    parser = argparse.ArgumentParser(description="Run EventAlpha hybrid pipeline: quantum subset + wait, classical sizing + guardrails.")
    parser.add_argument("--event-type", default="cpi")
    parser.add_argument("--title", default="Manual EventAlpha hybrid event")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--confidence-threshold", type=float, default=0.70)
    parser.add_argument("--risk-budget", type=float, default=0.02)
    parser.add_argument("--no-learning-log", action="store_true")
    args = parser.parse_args()

    report = run_hybrid_eventalpha(
        event_type=args.event_type,
        title=args.title,
        top_n=args.top_n,
        confidence_threshold=args.confidence_threshold,
        total_risk_budget=args.risk_budget,
        write_learning=not args.no_learning_log,
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved: {report['saved_to']}")


if __name__ == "__main__":
    main()

