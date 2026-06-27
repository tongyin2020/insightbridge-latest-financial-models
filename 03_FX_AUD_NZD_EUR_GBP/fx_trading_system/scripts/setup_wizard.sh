#!/bin/bash
# ============================================================================
# FX Trading System - Interactive Setup Wizard
# Guides users through initial configuration of all services.
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
ENV_FILE="$BACKEND_DIR/.env"

# ─── Colors ──────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

success()  { echo -e "${GREEN}$1${NC}"; }
warn()     { echo -e "${YELLOW}$1${NC}"; }
prompt()   { echo -e "${CYAN}$1${NC}"; }
error()    { echo -e "${RED}$1${NC}"; }
bold()     { echo -e "${BOLD}$1${NC}"; }

# ─── Banner ──────────────────────────────────────────────────────────────────

clear
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}║${BOLD}          FX Trading System - Setup Wizard              ${NC}${CYAN}║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}║${NC}   AUD/USD & NZD/USD automated trading platform            ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}   with event-driven signals and real-time dashboards       ${CYAN}║${NC}"
echo -e "${CYAN}║                                                              ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── Collect values with defaults ────────────────────────────────────────────

TWELVE_DATA_KEY=""
TELEGRAM_TOKEN=""
TELEGRAM_CHAT=""
DUKASCOPY_ENABLED="n"
DUKASCOPY_ACCOUNT_TYPE="demo"
IB_ENABLED="n"
IB_HOST="127.0.0.1"
IB_PORT="7497"
IB_CLIENT_ID="1"

# ─── Step 1: Prerequisites ──────────────────────────────────────────────────

bold "Step 1/6: Checking prerequisites..."
echo ""

# Python
PYTHON_OK=false
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 9 ]; then
        success "  [OK] Python $PY_VERSION (>= 3.9 required)"
        PYTHON_OK=true
    else
        error "  [!!] Python $PY_VERSION found, but 3.9+ is required"
    fi
else
    error "  [!!] Python 3 not found. Please install Python 3.9+"
fi

# Node.js
NODE_OK=false
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version 2>&1)
    success "  [OK] Node.js $NODE_VERSION"
    NODE_OK=true
else
    error "  [!!] Node.js not found. Please install Node.js 18+ for the dashboard."
    warn "       Frontend will not work without Node.js."
fi

# npm
NPM_OK=false
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version 2>&1)
    success "  [OK] npm $NPM_VERSION"
    NPM_OK=true
else
    warn "  [--] npm not found (needed for frontend)"
fi

# Java (optional for Dukascopy)
if command -v java &> /dev/null; then
    JAVA_VERSION=$(java -version 2>&1 | head -n1)
    success "  [OK] Java found - Dukascopy adapter available"
else
    warn "  [--] Java not found (optional - only needed for Dukascopy JForex adapter)"
fi

echo ""

if [ "$PYTHON_OK" = false ]; then
    error "Python 3.9+ is required. Please install it and re-run this wizard."
    exit 1
fi

# ─── Step 2: Twelve Data API ────────────────────────────────────────────────

bold "Step 2/6: Market Data - Twelve Data API"
echo ""
prompt "  Register for free at https://twelvedata.com (800 requests/day free)"
prompt "  A free account is sufficient for AUD/USD and NZD/USD 1-minute data."
echo ""
read -p "$(echo -e "${CYAN}  Enter your Twelve Data API key (or press Enter to skip): ${NC}")" TWELVE_DATA_KEY

if [ -z "$TWELVE_DATA_KEY" ]; then
    warn "  -> Skipped. The system will use simulated market data."
    TWELVE_DATA_KEY="your_twelve_data_key_here"
else
    success "  -> API key saved. Live market data will be used."
fi
echo ""

# ─── Step 3: Telegram Bot ───────────────────────────────────────────────────

bold "Step 3/6: Telegram Trade Alerts (optional)"
echo ""
prompt "  To receive trade alerts via Telegram:"
prompt "  1. Open Telegram, search @BotFather"
prompt "  2. Send /newbot, name it 'FX Trading Alerts'"
prompt "  3. Copy the bot token"
echo ""
read -p "$(echo -e "${CYAN}  Enter your Telegram bot token (or press Enter to skip): ${NC}")" TELEGRAM_TOKEN

if [ -z "$TELEGRAM_TOKEN" ]; then
    warn "  -> Skipped. Trade alerts will only appear in the dashboard."
    TELEGRAM_TOKEN="your_telegram_bot_token_here"
    TELEGRAM_CHAT="your_chat_id_here"
else
    success "  -> Bot token saved."
    echo ""
    prompt "  To get your chat ID:"
    prompt "  1. Send any message to your new bot in Telegram"
    prompt "  2. Visit: https://api.telegram.org/bot${TELEGRAM_TOKEN}/getUpdates"
    prompt "  3. Look for \"chat\":{\"id\":XXXXXXX} in the response"
    echo ""
    read -p "$(echo -e "${CYAN}  Enter your Telegram chat ID (or press Enter to skip): ${NC}")" TELEGRAM_CHAT
    if [ -z "$TELEGRAM_CHAT" ]; then
        warn "  -> Skipped chat ID. You can add it later in backend/.env"
        TELEGRAM_CHAT="your_chat_id_here"
    else
        success "  -> Chat ID saved. Telegram alerts are fully configured."
    fi
fi
echo ""

# ─── Step 4: Dukascopy ──────────────────────────────────────────────────────

bold "Step 4/6: Dukascopy Broker (optional)"
echo ""
read -p "$(echo -e "${CYAN}  Do you have a Dukascopy account? (y/n): ${NC}")" DUKASCOPY_ENABLED

if [ "$DUKASCOPY_ENABLED" = "y" ] || [ "$DUKASCOPY_ENABLED" = "Y" ]; then
    read -p "$(echo -e "${CYAN}  Is this a Demo or Live account? (demo/live): ${NC}")" DUKASCOPY_ACCOUNT_TYPE
    DUKASCOPY_ACCOUNT_TYPE=$(echo "$DUKASCOPY_ACCOUNT_TYPE" | tr '[:upper:]' '[:lower:]')
    if [ "$DUKASCOPY_ACCOUNT_TYPE" = "live" ]; then
        echo ""
        warn "  *** WARNING: Live trading involves real money. ***"
        warn "  *** Use demo mode first to validate your strategy. ***"
        warn "  *** Start with minimum position sizes. ***"
        echo ""
        read -p "$(echo -e "${YELLOW}  I understand the risks and want to proceed with Live (yes/no): ${NC}")" LIVE_CONFIRM
        if [ "$LIVE_CONFIRM" != "yes" ]; then
            warn "  -> Switching to Demo mode for safety."
            DUKASCOPY_ACCOUNT_TYPE="demo"
        fi
    fi
    success "  -> Dukascopy configured in $DUKASCOPY_ACCOUNT_TYPE mode."
else
    warn "  -> Skipped. You can configure Dukascopy later."
    DUKASCOPY_ENABLED="n"
fi
echo ""

# ─── Step 5: Interactive Brokers ─────────────────────────────────────────────

bold "Step 5/6: Interactive Brokers TWS/Gateway (optional)"
echo ""
read -p "$(echo -e "${CYAN}  Do you have IB TWS or Gateway running? (y/n): ${NC}")" IB_ENABLED

if [ "$IB_ENABLED" = "y" ] || [ "$IB_ENABLED" = "Y" ]; then
    read -p "$(echo -e "${CYAN}  IB host [default: 127.0.0.1]: ${NC}")" IB_HOST_INPUT
    IB_HOST="${IB_HOST_INPUT:-127.0.0.1}"

    echo ""
    prompt "  Common ports: 7497 = TWS (paper), 7496 = TWS (live)"
    prompt "                4001 = Gateway (paper), 4002 = Gateway (live)"
    read -p "$(echo -e "${CYAN}  IB port [default: 7497]: ${NC}")" IB_PORT_INPUT
    IB_PORT="${IB_PORT_INPUT:-7497}"

    read -p "$(echo -e "${CYAN}  IB client ID [default: 1]: ${NC}")" IB_CLIENT_ID_INPUT
    IB_CLIENT_ID="${IB_CLIENT_ID_INPUT:-1}"

    success "  -> IB configured at $IB_HOST:$IB_PORT (client $IB_CLIENT_ID)."
else
    warn "  -> Skipped. You can configure IB later."
fi
echo ""

# ─── Step 6: Write .env file ────────────────────────────────────────────────

bold "Step 6/6: Writing configuration..."
echo ""

# Back up existing .env if present
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%d%H%M%S)"
    warn "  -> Existing .env backed up."
fi

cat > "$ENV_FILE" << ENVEOF
# FX Trading System Configuration
# Generated by setup_wizard.sh on $(date '+%Y-%m-%d %H:%M:%S')

# Market Data
TWELVE_DATA_API_KEY=$TWELVE_DATA_KEY

# Telegram Alerts
TELEGRAM_BOT_TOKEN=$TELEGRAM_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT

# Broker APIs
DUKASCOPY_API_URL=http://localhost:9090
DUKASCOPY_ACCOUNT_TYPE=$DUKASCOPY_ACCOUNT_TYPE
IB_TWS_HOST=$IB_HOST
IB_TWS_PORT=$IB_PORT
IB_TWS_CLIENT_ID=$IB_CLIENT_ID

# Server
HOST=0.0.0.0
PORT=8000

# Database
DATABASE_PATH=fx_trading.db
ENVEOF

success "  -> Configuration written to backend/.env"
echo ""

# ─── Install Python dependencies ────────────────────────────────────────────

bold "Installing Python dependencies..."
echo ""

cd "$BACKEND_DIR"

if [ ! -d "venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "  Installing packages from requirements.txt..."
if pip install -r requirements.txt --quiet 2>&1; then
    success "  -> Python dependencies installed."
else
    warn "  -> Some packages may have failed. Check above for errors."
fi
echo ""

# ─── Install Node.js dependencies ───────────────────────────────────────────

if [ "$NODE_OK" = true ] && [ "$NPM_OK" = true ]; then
    bold "Installing Node.js dependencies..."
    echo ""
    cd "$FRONTEND_DIR"
    if npm install --silent 2>&1; then
        success "  -> Frontend dependencies installed."
    else
        warn "  -> npm install had warnings. The frontend may still work."
    fi
    echo ""
else
    warn "Skipping frontend dependencies (Node.js/npm not available)."
    echo ""
fi

# ─── Initialize database ────────────────────────────────────────────────────

bold "Initializing database..."
echo ""

cd "$BACKEND_DIR"
source venv/bin/activate

python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')
from database import init_db
asyncio.run(init_db())
print('  Database initialized successfully.')
"

if [ $? -eq 0 ]; then
    success "  -> Database ready at backend/fx_trading.db"
else
    warn "  -> Database initialization had issues. It will be created on first run."
fi
echo ""

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                    Setup Complete!                            ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"

# Market data
if [ "$TWELVE_DATA_KEY" = "your_twelve_data_key_here" ]; then
    echo -e "${CYAN}║${NC}  Market Data:    ${YELLOW}Simulated (no API key)${NC}                      ${CYAN}║${NC}"
else
    echo -e "${CYAN}║${NC}  Market Data:    ${GREEN}Twelve Data API (live)${NC}                      ${CYAN}║${NC}"
fi

# Telegram
if [ "$TELEGRAM_TOKEN" = "your_telegram_bot_token_here" ]; then
    echo -e "${CYAN}║${NC}  Telegram:       ${YELLOW}Not configured${NC}                              ${CYAN}║${NC}"
elif [ "$TELEGRAM_CHAT" = "your_chat_id_here" ]; then
    echo -e "${CYAN}║${NC}  Telegram:       ${YELLOW}Partial (missing chat ID)${NC}                   ${CYAN}║${NC}"
else
    echo -e "${CYAN}║${NC}  Telegram:       ${GREEN}Fully configured${NC}                            ${CYAN}║${NC}"
fi

# Dukascopy
if [ "$DUKASCOPY_ENABLED" = "y" ] || [ "$DUKASCOPY_ENABLED" = "Y" ]; then
    echo -e "${CYAN}║${NC}  Dukascopy:      ${GREEN}${DUKASCOPY_ACCOUNT_TYPE} account${NC}                              ${CYAN}║${NC}"
else
    echo -e "${CYAN}║${NC}  Dukascopy:      ${YELLOW}Not configured${NC}                              ${CYAN}║${NC}"
fi

# Interactive Brokers
if [ "$IB_ENABLED" = "y" ] || [ "$IB_ENABLED" = "Y" ]; then
    echo -e "${CYAN}║${NC}  IB TWS/Gateway: ${GREEN}${IB_HOST}:${IB_PORT}${NC}                            ${CYAN}║${NC}"
else
    echo -e "${CYAN}║${NC}  IB TWS/Gateway: ${YELLOW}Not configured${NC}                              ${CYAN}║${NC}"
fi

echo -e "${CYAN}║${NC}                                                              ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Config file:    backend/.env                                ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  Database:       backend/fx_trading.db                       ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ─── Launch? ─────────────────────────────────────────────────────────────────

read -p "$(echo -e "${CYAN}Start the system now? (y/n): ${NC}")" START_NOW

if [ "$START_NOW" = "y" ] || [ "$START_NOW" = "Y" ]; then
    echo ""
    success "Launching FX Trading System..."
    echo ""
    exec "$SCRIPT_DIR/start_all.sh"
else
    echo ""
    success "Setup complete! To start later, run:"
    echo "  cd \"$(dirname "$SCRIPT_DIR")\""
    echo "  ./scripts/start_all.sh"
    echo ""
fi
