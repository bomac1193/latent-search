#!/bin/bash
# Latent Search - Quick Start Script
# Starts both backend and frontend servers

set -e

echo "==================================="
echo "  Latent Search - Diagnostic Tool"
echo "==================================="

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Backend setup
echo ""
echo "[Backend] Setting up..."
cd "$SCRIPT_DIR/backend"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[Backend] Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "[Backend] Installing dependencies..."
pip install -q -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[Backend] Created .env from .env.example"
        echo "[Backend] WARNING: Please edit .env with your Spotify credentials"
    fi
fi

# Frontend setup
echo ""
echo "[Frontend] Setting up..."
cd "$SCRIPT_DIR/frontend"

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "[Frontend] Installing dependencies..."
    npm install
fi

# Start servers
echo ""
echo "==================================="
echo "  Starting servers..."
echo "==================================="

# Start backend in background
cd "$SCRIPT_DIR/backend"
source venv/bin/activate
echo "[Backend] Starting on http://localhost:8000"
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

# Wait for backend to start
sleep 2

# Start frontend
cd "$SCRIPT_DIR/frontend"
echo "[Frontend] Starting on http://localhost:5173"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "==================================="
echo "  Latent Search is running!"
echo "==================================="
echo ""
echo "  Frontend: http://localhost:5173"
echo "  Backend:  http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop all servers"
echo ""

# Trap Ctrl+C to kill both processes
trap "echo ''; echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

# Wait for either process to exit
wait
