#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path
import re


DEFAULT_BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")

CODE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".sql",
    ".sh",
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
}

EXCLUDE_PATTERNS = [
    ".git/*",
    "__pycache__/*",
    "node_modules/*",
    "dist/*",
    "build/*",
]

EXCLUDE_PARTS = {
    ".git",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}

CATEGORIES = {
    "hotel_model_names": [
        r"\bMARE\b",
        r"\bDirector\b",
        r"\bSelfACQ\b",
        r"\bPOLARIS\b",
        r"\bORION\b",
        r"\bNOVA\b",
    ],
    "hotel_project_paths": [
        r"InsightBridge_Final_Three_Models",
        r"InsightBridge_九大模型_v2026",
        r"final_three_models_release_20260625",
        r"Hotel_Model_Rvisions",
    ],
    "hotel_kpi_terms": [
        r"\bRevPAR\b",
        r"\bTRevPAR\b",
        r"\bADR\b",
        r"\boccupancy\b",
        r"Average Room Rate",
        r"Macau hotel",
        r"hotel model",
        r"\bDSEC\b",
        r"\bMHA\b",
    ],
}


def should_skip(path: Path, base: Path) -> bool:
    rel = path.relative_to(base)
    rel_str = rel.as_posix()
    if path.name == "check_finance_project_contamination.py":
        return True
    if any(part in EXCLUDE_PARTS for part in rel.parts):
        return True
    return any(fnmatch.fnmatch(rel_str, pattern) for pattern in EXCLUDE_PATTERNS)


def iter_candidate_files(base: Path):
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path, base):
            continue
        if path.suffix.lower() in CODE_EXTENSIONS or path.name in {"README", "Dockerfile"}:
            yield path


def scan_file(path: Path, base: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    hits = []
    lines = text.splitlines()
    for category, needles in CATEGORIES.items():
        for lineno, line in enumerate(lines, start=1):
            for needle in needles:
                if re.search(needle, line):
                    hits.append(
                        {
                            "category": category,
                            "needle": needle,
                            "file": str(path.relative_to(base)),
                            "line": lineno,
                            "text": line.strip(),
                        }
                    )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether hotel-model terms or paths leaked into the finance project."
    )
    parser.add_argument("--base", default=str(DEFAULT_BASE), help="Finance project root to scan.")
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show every hit instead of only the first few per category.",
    )
    args = parser.parse_args()

    base = Path(args.base).expanduser().resolve()
    if not base.exists():
        print(f"[ERROR] base path not found: {base}")
        return 2

    all_hits = []
    file_count = 0
    for file_path in iter_candidate_files(base):
        file_count += 1
        all_hits.extend(scan_file(file_path, base))

    print("InsightBridge Finance Contamination Check")
    print("=" * 60)
    print(f"base: {base}")
    print(f"files_scanned: {file_count}")
    print("-" * 60)

    if not all_hits:
        print("status: CLEAN")
        print("message: no hotel-model names, project paths, or KPI terms were found in scanned finance project files.")
        return 0

    print("status: ATTENTION")
    print(f"total_hits: {len(all_hits)}")
    print("-" * 60)

    for category in CATEGORIES:
        category_hits = [hit for hit in all_hits if hit["category"] == category]
        print(f"[{category}] hits={len(category_hits)}")
        limit = len(category_hits) if args.show_all else min(12, len(category_hits))
        for hit in category_hits[:limit]:
            print(f"- {hit['file']}:{hit['line']} | needle={hit['needle']} | {hit['text']}")
        if category_hits and not args.show_all and len(category_hits) > limit:
            print(f"- ... {len(category_hits) - limit} more hit(s), rerun with --show-all to expand")
        print("-" * 60)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
