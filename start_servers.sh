#!/bin/bash

# Start both Frontend and Backend servers
# Usage: ./start_servers.sh

echo "🏀 Starting NBA Betting Analytics Servers..."
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check if a port is in use
check_port() {
    lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1
}

# Check if backend port is already in use
if check_port 8000; then
    echo "⚠️  Port 8000 is already in use. Backend may already be running."
else
    echo -e "${BLUE}Starting Backend (FastAPI) on http://localhost:8000${NC}"
    cd backend
    # Activate venv if it exists
    if [ -d "venv" ]; then
        source venv/bin/activate
    fi
    python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
    echo -e "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"
    cd ..
fi

# Wait a moment for backend to start
sleep 2

# Check if frontend port is already in use
if check_port 5173; then
    echo "⚠️  Port 5173 is already in use. Frontend may already be running."
else
    echo -e "${BLUE}Starting Frontend (Vite) on http://localhost:5173${NC}"
    cd frontend
    npm run dev &
    FRONTEND_PID=$!
    echo -e "${GREEN}✅ Frontend started (PID: $FRONTEND_PID)${NC}"
    cd ..
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Both servers are running!${NC}"
echo ""
echo "Backend API:  http://localhost:8000"
echo "Backend Docs: http://localhost:8000/docs"
echo "Frontend:     http://localhost:5173"
echo ""
echo "To stop the servers, press Ctrl+C or run:"
echo "  kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "Waiting for servers to be ready..."
sleep 3

# Keep script running
wait
