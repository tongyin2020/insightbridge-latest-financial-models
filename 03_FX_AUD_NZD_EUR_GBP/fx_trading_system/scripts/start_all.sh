#!/bin/bash
# FX Trading System - Start All Services
# Usage: ./start_all.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "  FX Trading System - Full Stack"
echo "========================================="
echo ""
echo "Starting all services..."
echo ""

# Start backend in background
echo "[1/2] Starting backend..."
"$SCRIPT_DIR/start_backend.sh" &
BACKEND_PID=$!
sleep 3

# Start frontend in background
echo "[2/2] Starting frontend..."
"$SCRIPT_DIR/start_frontend.sh" &
FRONTEND_PID=$!

echo ""
echo "========================================="
echo "  All services started!"
echo "========================================="
echo ""
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo "  Frontend: http://localhost:3000"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# Wait for any process to exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
