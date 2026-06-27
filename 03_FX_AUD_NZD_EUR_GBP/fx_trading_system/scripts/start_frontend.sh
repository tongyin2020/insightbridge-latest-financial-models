#!/bin/bash
# FX Trading System - Frontend Startup Script
# Usage: ./start_frontend.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "========================================="
echo "  FX Trading System - Frontend"
echo "========================================="

cd "$FRONTEND_DIR"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "ERROR: node not found. Please install Node.js 18+"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# Start dev server
echo ""
echo "Starting React frontend on http://localhost:3000"
echo "Backend proxy -> http://localhost:8000"
echo ""
npm run dev
