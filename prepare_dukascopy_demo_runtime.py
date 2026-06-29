#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
RUNTIME_DIR = BASE / "dukascopy_runtime"
JFOREX_HOME = Path.home() / "JForex4"
DIRS = {
    "runtime": RUNTIME_DIR,
    "sdk": RUNTIME_DIR / "sdk",
    "lib": RUNTIME_DIR / "lib",
    "src": RUNTIME_DIR / "src",
    "build": RUNTIME_DIR / "build",
    "logs": RUNTIME_DIR / "logs",
    "reports": RUNTIME_DIR / "reports",
}


def scan_candidates() -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {
        "sdk_jars": [],
        "jnlp_jars": [],
        "jforex_apps": [],
        "java_bins": [],
        "compiler_jars": [],
        "lib_dirs": [],
    }

    known_jforex_app = JFOREX_HOME / "JForex4.app"
    if known_jforex_app.exists():
        candidates["jforex_apps"].append(str(known_jforex_app))

    known_java = JFOREX_HOME / ".install4j" / "jre.bundle" / "Contents" / "Home" / "bin" / "java"
    if known_java.exists():
        candidates["java_bins"].append(str(known_java))

    for lib_root in [JFOREX_HOME / "libs" / "demo", JFOREX_HOME / "libs" / "live"]:
        if not lib_root.exists():
            continue
        for version_dir in sorted([p for p in lib_root.iterdir() if p.is_dir()]):
            candidates["lib_dirs"].append(str(version_dir))
            for jar in version_dir.glob("*.jar"):
                name = jar.name.lower()
                if "sdk" in name or "dukascopy" in name or "jforex" in name:
                    candidates["sdk_jars"].append(str(jar))
                if name.startswith("ecj-"):
                    candidates["compiler_jars"].append(str(jar))
            for jnlp in version_dir.glob("*.jnlp"):
                candidates["jnlp_jars"].append(str(jnlp))

    for root in [RUNTIME_DIR / "sdk", RUNTIME_DIR / "lib", Path.home() / "Downloads"]:
        if not root.exists():
            continue
        for pattern in ("*dukascopy*.jar", "*jforex*.jar", "*sdk*.jar", "*.jnlp", "*JForex*.dmg", "*dukascopy*.dmg"):
            for path in root.glob(pattern):
                name = path.name.lower()
                if path.suffix.lower() == ".jar":
                    candidates["sdk_jars"].append(str(path))
                    if name.startswith("ecj-"):
                        candidates["compiler_jars"].append(str(path))
                elif path.suffix.lower() == ".jnlp":
                    candidates["jnlp_jars"].append(str(path))
    for key in candidates:
        candidates[key] = sorted(set(candidates[key]))
    return candidates


def main() -> int:
    for path in DIRS.values():
        path.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": str(BASE),
        "runtime_dir": str(RUNTIME_DIR),
        "created_dirs": {key: str(path) for key, path in DIRS.items()},
        "detected_candidates": scan_candidates(),
    }
    out = RUNTIME_DIR / "reports" / "prepare_dukascopy_demo_runtime.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Prepared Dukascopy demo runtime")
    print("=" * 60)
    print(f"runtime_dir: {RUNTIME_DIR}")
    print(f"report: {out}")
    for key, items in payload["detected_candidates"].items():
        print(f"{key}: {len(items)}")
        for item in items[:10]:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
