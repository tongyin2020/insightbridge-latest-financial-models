#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
ENV_FILE="$BASE/.env.dukascopy_demo.local"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"
RUNTIME="$BASE/dukascopy_runtime"
SRC="$RUNTIME/src/DukascopyDemoConnectCheck.java"
BUILD="$RUNTIME/build"
SDK_DIR="$RUNTIME/sdk"
PREP_REPORT="$RUNTIME/reports/prepare_dukascopy_demo_runtime.json"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

"$PY" "$BASE/prepare_dukascopy_demo_runtime.py" >/dev/null

detect_json() {
  local key="$1"
  "$PY" - "$PREP_REPORT" "$key" <<'PY'
import json
import sys
from pathlib import Path

report = Path(sys.argv[1])
key = sys.argv[2]
if not report.exists():
    raise SystemExit(0)
payload = json.loads(report.read_text(encoding="utf-8"))
items = payload.get("detected_candidates", {}).get(key, [])
if isinstance(items, list) and items:
    print(items[0])
PY
}

JAVA_BIN="${DUKASCOPY_JAVA_BIN:-}"
if [[ -z "$JAVA_BIN" ]]; then
  JAVA_BIN="$(detect_json java_bins)"
fi
if [[ -z "$JAVA_BIN" ]]; then
  JAVA_BIN="/usr/bin/java"
fi

JAVAC_BIN="${DUKASCOPY_JAVAC_BIN:-/usr/bin/javac}"
SDK_JAR="${DUKASCOPY_JFOREX_SDK_JAR:-}"
COMPILER_JAR="${DUKASCOPY_JAVA_COMPILER_JAR:-}"

if [[ -z "$SDK_JAR" ]]; then
  SDK_JAR="$("$PY" - "$PREP_REPORT" <<'PY'
import json
import sys
from pathlib import Path

report = Path(sys.argv[1])
if not report.exists():
    raise SystemExit(0)
payload = json.loads(report.read_text(encoding="utf-8"))
for item in payload.get("detected_candidates", {}).get("sdk_jars", []):
    name = Path(item).name.lower()
    if "jforex-api" in name or "jforex4" in name:
        print(item)
        break
PY
)"
fi

if [[ -z "$COMPILER_JAR" ]]; then
  COMPILER_JAR="$(detect_json compiler_jars)"
fi

LIB_DIR=""
if [[ -n "$SDK_JAR" ]]; then
  LIB_DIR="$(dirname "$SDK_JAR")"
fi

if [[ ! -x "$JAVA_BIN" ]]; then
  echo "Java runtime not found: $JAVA_BIN"
  exit 1
fi

if [[ -z "$SDK_JAR" || ! -f "$SDK_JAR" ]]; then
  echo "No Dukascopy SDK jar found."
  echo "Put the SDK jar in: $SDK_DIR"
  exit 1
fi

mkdir -p "$BUILD"

CLASSPATH="$SDK_JAR"
if [[ -n "$LIB_DIR" && -d "$LIB_DIR" ]]; then
  while IFS= read -r jar; do
    CLASSPATH="$CLASSPATH:$jar"
  done < <(find "$LIB_DIR" -type f -name '*.jar' | sort)
fi

echo "Compiling Dukascopy demo connect check..."
if [[ -x "$JAVAC_BIN" ]] && "$JAVAC_BIN" -version >/dev/null 2>&1; then
  "$JAVAC_BIN" -cp "$CLASSPATH" -d "$BUILD" "$SRC"
elif [[ -n "$COMPILER_JAR" && -f "$COMPILER_JAR" ]]; then
  "$JAVA_BIN" -jar "$COMPILER_JAR" -1.8 -cp "$CLASSPATH" -d "$BUILD" "$SRC"
else
  echo "No Java compiler available. Missing both javac and ecj compiler jar."
  exit 1
fi

echo "Running Dukascopy demo connect check..."
"$JAVA_BIN" -cp "$BUILD:$CLASSPATH" DukascopyDemoConnectCheck
