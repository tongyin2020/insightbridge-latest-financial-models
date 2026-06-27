#!/bin/bash
#
# Build script for Dukascopy JForex FX Trading Adapter
# Compiles the bridge strategy and packages it as a JAR.
#

set -e

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAR_NAME="fx-trading-adapter.jar"
BUILD_DIR="${SCRIPT_DIR}/build"

echo ""
echo "========================================"
echo "  Dukascopy JForex Adapter - Build"
echo "========================================"
echo ""

# --- Check Java ---
echo -e "${YELLOW}[1/4]${NC} Checking Java installation..."

if ! command -v java &>/dev/null; then
    echo -e "${RED}[FAIL]${NC} Java is not installed or not in PATH."
    echo ""
    echo "  Please install Java JDK 8 or later:"
    echo "    macOS:  brew install openjdk@17"
    echo "    Linux:  sudo apt install openjdk-17-jdk"
    echo "    Or download from: https://adoptium.net/"
    echo ""
    exit 1
fi

JAVA_VERSION=$(java -version 2>&1 | head -n1)
echo -e "${GREEN}[OK]${NC}   Java found: ${JAVA_VERSION}"

if ! command -v javac &>/dev/null; then
    echo -e "${RED}[FAIL]${NC} javac not found. You need the JDK, not just the JRE."
    echo "  Install a JDK (e.g., brew install openjdk@17)"
    exit 1
fi

echo -e "${GREEN}[OK]${NC}   javac found."

# --- Check JAVA_HOME ---
if [ -z "$JAVA_HOME" ]; then
    echo -e "${YELLOW}[WARN]${NC} JAVA_HOME is not set. Relying on PATH for java/javac."
else
    echo -e "${GREEN}[OK]${NC}   JAVA_HOME=${JAVA_HOME}"
fi

echo ""

# --- Locate JForex SDK ---
echo -e "${YELLOW}[2/4]${NC} Locating JForex SDK..."

JFOREX_LIBS=""

SEARCH_DIRS=(
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
        FOUND_JARS=$(find "$dir" -maxdepth 2 -name "*.jar" 2>/dev/null | head -1)
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

if [ -f "${SCRIPT_DIR}/DukascopyBridgeStrategy.java" ]; then
    SOURCES+=("${SCRIPT_DIR}/DukascopyBridgeStrategy.java")
else
    echo -e "${RED}[FAIL]${NC} DukascopyBridgeStrategy.java not found in ${SCRIPT_DIR}"
    exit 1
fi

if [ -f "${SCRIPT_DIR}/HttpClient.java" ]; then
    SOURCES+=("${SCRIPT_DIR}/HttpClient.java")
else
    echo -e "${RED}[FAIL]${NC} HttpClient.java not found in ${SCRIPT_DIR}"
    exit 1
fi

mkdir -p "$BUILD_DIR"

if javac -cp "$CLASSPATH" -d "$BUILD_DIR" "${SOURCES[@]}"; then
    echo -e "${GREEN}[OK]${NC}   Compilation successful."
else
    echo -e "${RED}[FAIL]${NC} Compilation failed. Check errors above."
    exit 1
fi

echo ""

# --- Package JAR ---
echo -e "${YELLOW}[4/4]${NC} Packaging ${JAR_NAME}..."

if jar cf "${SCRIPT_DIR}/${JAR_NAME}" -C "$BUILD_DIR" .; then
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
echo "  Output: ${SCRIPT_DIR}/${JAR_NAME}"
echo ""
echo "  To load into JForex platform:"
echo "  1. Open JForex trading platform"
echo "  2. Go to Strategies -> Local tab"
echo "  3. Click 'Add Strategy' or drag the JAR file in"
echo "  4. Select DukascopyBridgeStrategy as the strategy"
echo "  5. Configure the HTTP endpoint in strategy parameters"
echo "  6. Start the strategy on the desired instrument"
echo ""
echo "  The strategy will forward tick data and OHLC bars"
echo "  to the FX Trading System backend via HTTP."
echo ""
