#!/bin/bash
# FX Trading System - Backend Startup Script
# Usage: ./start_backend.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"

echo "========================================="
echo "  FX Trading System - Backend"
echo "========================================="

cd "$BACKEND_DIR"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.10+"
    exit 1
fi

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Create .env from example if not exists
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "NOTE: Edit .env to add your API keys (Twelve Data, Telegram, etc.)"
    echo "      Without API keys, the system will use simulated data."
fi

# Start the server
echo ""
echo "Starting FastAPI backend on http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
echo "WebSocket: ws://localhost:8000/ws"
echo ""
python3 main.py
