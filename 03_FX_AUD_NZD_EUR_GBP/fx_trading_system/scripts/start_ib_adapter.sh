#!/bin/bash
# FX Trading System - IB TWS Adapter Startup Script
# Usage: ./start_ib_adapter.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IB_DIR="$PROJECT_DIR/adapters/ib_tws"

echo "========================================="
echo "  FX Trading System - IB TWS Adapter"
echo "========================================="

cd "$IB_DIR"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt --quiet

echo ""
echo "Starting IB TWS Adapter..."
echo "Make sure TWS/Gateway is running with API enabled on port 7497"
echo ""
python3 ib_adapter.py
