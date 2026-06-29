#!/bin/bash
#
# Build script for Dukascopy JForex FX Trading Adapter
# Compiles the bridge strategy and packages it as a JAR.
#

set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STRATEGY_SOURCE="${STRATEGY_SOURCE:-DukascopyBridgeStrategy.java}"
JAR_NAME="${JAR_NAME:-fx-trading-adapter.jar}"
BUILD_DIR="${SCRIPT_DIR}/build"
JFOREX_HOME="${JFOREX_HOME:-$HOME/JForex4}"
JFOREX_BUNDLED_JAVA="${JFOREX_HOME}/.install4j/jre.bundle/Contents/Home/bin/java"
JFOREX_BUNDLED_JAR="${JFOREX_HOME}/.install4j/jre.bundle/Contents/Home/bin/jar"
JFOREX_DEMO_LIBS="${JFOREX_HOME}/libs/demo/4.8.15"
JFOREX_LIVE_LIBS="${JFOREX_HOME}/libs/live/4.8.14"

echo ""
echo "========================================"
echo "  Dukascopy JForex Adapter - Build"
echo "========================================"
echo ""

# --- Check Java ---
echo -e "${YELLOW}[1/4]${NC} Checking Java installation..."

JAVA_BIN=""
JAVAC_BIN=""
ECJ_JAR=""
JAR_BIN=""

if [[ -x "$JFOREX_BUNDLED_JAVA" ]]; then
    JAVA_BIN="$JFOREX_BUNDLED_JAVA"
    echo -e "${GREEN}[OK]${NC}   Using JForex bundled Java."
elif command -v java >/dev/null 2>&1; then
    JAVA_BIN="$(command -v java)"
    echo -e "${GREEN}[OK]${NC}   Using system Java: ${JAVA_BIN}"
else
    echo -e "${RED}[FAIL]${NC} Java is not installed or not found."
    exit 1
fi

JAVA_VERSION=$("$JAVA_BIN" -version 2>&1 | head -n1)
echo -e "${GREEN}[OK]${NC}   Java found: ${JAVA_VERSION}"

if [[ -x "$JFOREX_BUNDLED_JAR" ]]; then
    JAR_BIN="$JFOREX_BUNDLED_JAR"
elif command -v zip >/dev/null 2>&1; then
    JAR_BIN="$(command -v zip)"
elif command -v jar >/dev/null 2>&1; then
    JAR_BIN="$(command -v jar)"
else
    echo -e "${RED}[FAIL]${NC} jar/zip packaging tool not found."
    exit 1
fi

if command -v javac >/dev/null 2>&1 && javac -version >/dev/null 2>&1; then
    JAVAC_BIN="$(command -v javac)"
    echo -e "${GREEN}[OK]${NC}   javac found: ${JAVAC_BIN}"
else
    for ecj in "$JFOREX_DEMO_LIBS"/ecj-*.jar "$JFOREX_LIVE_LIBS"/ecj-*.jar; do
        if [[ -f "$ecj" ]]; then
            ECJ_JAR="$ecj"
            break
        fi
    done
    if [[ -n "$ECJ_JAR" ]]; then
        echo -e "${GREEN}[OK]${NC}   Using ECJ compiler: ${ECJ_JAR}"
    else
        echo -e "${RED}[FAIL]${NC} No Java compiler found (javac or ECJ)."
        exit 1
    fi
fi

# --- Check JAVA_HOME ---
if [ -z "${JAVA_HOME:-}" ]; then
    echo -e "${YELLOW}[WARN]${NC} JAVA_HOME is not set. Relying on PATH for java/javac."
else
    echo -e "${GREEN}[OK]${NC}   JAVA_HOME=${JAVA_HOME}"
fi

echo ""

# --- Locate JForex SDK ---
echo -e "${YELLOW}[2/4]${NC} Locating JForex SDK..."

JFOREX_LIBS=""

SEARCH_DIRS=(
    "${JFOREX_HOME}/libs/demo"
    "${JFOREX_HOME}/libs/live"
    "${JFOREX_HOME}/libs"
    "${JFOREX_HOME}"
    "${HOME}/JForex/libs"
    "${HOME}/.jforex/libs"
    "/Applications/JForex/libs"
    "/Applications/JForex"
)

for dir in "${SEARCH_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        # Look for JForex API jars
        FOUND_JARS=$(find "$dir" -maxdepth 3 -name "*.jar" 2>/dev/null | head -1)
        if [ -n "$FOUND_JARS" ]; then
            JFOREX_LIBS="$dir"
            echo -e "${GREEN}[OK]${NC}   Found JForex SDK in: ${JFOREX_LIBS}"
            break
        fi
    fi
done

if [ -z "$JFOREX_LIBS" ]; then
    echo -e "${RED}[FAIL]${NC} JForex SDK not found."
    echo ""
    echo "  ============================================="
    echo "  JForex SDK Setup Instructions"
    echo "  ============================================="
    echo ""
    echo "  1. Download JForex trading platform from:"
    echo "     https://www.dukascopy.com/europe/en/forex/jforex/"
    echo ""
    echo "  2. Install and run JForex at least once."
    echo "     The SDK JARs will be downloaded to one of:"
    echo "       ~/JForex/libs/"
    echo "       ~/.jforex/libs/"
    echo ""
    echo "  3. Set the JFOREX_HOME environment variable:"
    echo "     export JFOREX_HOME=\$HOME/JForex"
    echo "     (Add this to your ~/.bashrc or ~/.zshrc)"
    echo ""
    echo "  4. Key JAR files needed:"
    echo "     - JForex-API-*.jar"
    echo "     - JForex-SDK-*.jar"
    echo ""
    echo "  5. Manual compilation (once you have the JARs):"
    echo "     CLASSPATH=\"/path/to/jforex/libs/*\""
    echo "     javac -cp \"\$CLASSPATH\" ${SCRIPT_DIR}/DukascopyBridgeStrategy.java ${SCRIPT_DIR}/HttpClient.java"
    echo "     jar cf ${JAR_NAME} -C ${SCRIPT_DIR} ."
    echo ""
    exit 1
fi

# Build classpath from all JARs in the SDK directory
CLASSPATH=$(find "$JFOREX_LIBS" -maxdepth 2 -name "*.jar" 2>/dev/null | tr '\n' ':')

if [ -z "$CLASSPATH" ]; then
    echo -e "${RED}[FAIL]${NC} No JAR files found in ${JFOREX_LIBS}"
    exit 1
fi

echo -e "${GREEN}[OK]${NC}   Classpath built with $(echo "$CLASSPATH" | tr ':' '\n' | grep -c '.jar') JARs."
echo ""

# --- Compile ---
echo -e "${YELLOW}[3/4]${NC} Compiling Java sources..."

SOURCES=()

if [ -f "${SCRIPT_DIR}/${STRATEGY_SOURCE}" ]; then
    SOURCES+=("${SCRIPT_DIR}/${STRATEGY_SOURCE}")
else
    echo -e "${RED}[FAIL]${NC} ${STRATEGY_SOURCE} not found in ${SCRIPT_DIR}"
    exit 1
fi

if [ -f "${SCRIPT_DIR}/HttpClient.java" ]; then
    SOURCES+=("${SCRIPT_DIR}/HttpClient.java")
else
    echo -e "${RED}[FAIL]${NC} HttpClient.java not found in ${SCRIPT_DIR}"
    exit 1
fi

mkdir -p "$BUILD_DIR"

if [[ -n "$JAVAC_BIN" ]]; then
    "$JAVAC_BIN" -cp "$CLASSPATH" -d "$BUILD_DIR" "${SOURCES[@]}"
elif [[ -n "$ECJ_JAR" ]]; then
    "$JAVA_BIN" -jar "$ECJ_JAR" -1.8 -cp "$CLASSPATH" -d "$BUILD_DIR" "${SOURCES[@]}"
else
    echo -e "${RED}[FAIL]${NC} No compiler available."
    exit 1
fi

if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}[OK]${NC}   Compilation successful."
else
    echo -e "${RED}[FAIL]${NC} Compilation failed. Check errors above."
    exit 1
fi

echo ""

# --- Package JAR ---
echo -e "${YELLOW}[4/4]${NC} Packaging ${JAR_NAME}..."

rm -f "${SCRIPT_DIR}/${JAR_NAME}"
if [[ "$(basename "$JAR_BIN")" == "zip" ]]; then
    (
        cd "$BUILD_DIR"
        "$JAR_BIN" -qr "${SCRIPT_DIR}/${JAR_NAME}" .
    )
elif "$JAR_BIN" cf "${SCRIPT_DIR}/${JAR_NAME}" -C "$BUILD_DIR" .; then
    true
else
    echo -e "${RED}[FAIL]${NC} Failed to create JAR file."
    exit 1
fi

if [[ -f "${SCRIPT_DIR}/${JAR_NAME}" ]]; then
    JAR_SIZE=$(du -h "${SCRIPT_DIR}/${JAR_NAME}" | cut -f1)
    echo -e "${GREEN}[OK]${NC}   Created ${SCRIPT_DIR}/${JAR_NAME} (${JAR_SIZE})"
else
    echo -e "${RED}[FAIL]${NC} Failed to create JAR file."
    exit 1
fi

echo ""

# --- Done ---
echo "========================================"
echo -e "  ${GREEN}BUILD SUCCESSFUL${NC}"
echo "========================================"
echo ""
echo "  Strategy source: ${STRATEGY_SOURCE}"
echo "  Output: ${SCRIPT_DIR}/${JAR_NAME}"
echo ""
echo "  To load into JForex platform:"
echo "  1. Open JForex trading platform"
echo "  2. Go to Strategies -> Local tab"
echo "  3. Click 'Add Strategy' or drag the JAR file in"
echo "  4. Select the compiled strategy class from ${STRATEGY_SOURCE}"
echo "  5. Configure the HTTP endpoint in strategy parameters"
echo "  6. Start the strategy on the desired instrument"
echo ""
echo "  The strategy will forward data to the FX Trading System backend via HTTP."
echo ""
