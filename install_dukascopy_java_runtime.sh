#!/bin/zsh
set -euo pipefail

BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
PY="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

echo "Install Dukascopy Java Runtime"
echo "============================================================"
echo "This script first checks whether the existing JForex4 install already bundles Java."
echo

JFOREX_BUNDLED_JAVA="/Users/tongyin/JForex4/.install4j/jre.bundle/Contents/Home/bin/java"

if [[ -x "$JFOREX_BUNDLED_JAVA" ]]; then
  echo "Bundled JForex Java already exists:"
  "$JFOREX_BUNDLED_JAVA" -version 2>&1 | sed -n '1,3p'
elif /usr/bin/java -version >/dev/null 2>&1; then
  echo "Java runtime already exists:"
  /usr/bin/java -version 2>&1 | sed -n '1,3p'
else
  echo "Installing Temurin 21 via Homebrew..."
  brew install --cask temurin@21
fi

echo
echo "Rechecking Java..."
if [[ -x "$JFOREX_BUNDLED_JAVA" ]]; then
  "$JFOREX_BUNDLED_JAVA" -version 2>&1 | sed -n '1,3p' || true
else
  /usr/bin/java -version 2>&1 | sed -n '1,3p' || true
fi

echo
echo "Preparing Dukascopy runtime folders..."
"$PY" "$BASE/prepare_dukascopy_demo_runtime.py"

echo
echo "Next manual step:"
echo "1. Put Dukascopy / JForex SDK jars into:"
echo "   $BASE/dukascopy_runtime/sdk"
echo "2. Re-run:"
echo "   bash $BASE/run_dukascopy_demo_connect_check.sh"
