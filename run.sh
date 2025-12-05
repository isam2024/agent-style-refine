#!/bin/bash

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Ports
BACKEND_PORT=1443
FRONTEND_PORT=1442

# Stop any existing services on our ports
stop_services() {
    echo -e "${YELLOW}Stopping existing services...${NC}"

    # Kill processes on backend port
    local backend_pid=$(lsof -ti:$BACKEND_PORT 2>/dev/null)
    if [ -n "$backend_pid" ]; then
        echo -e "  Stopping backend (PID: $backend_pid)..."
        kill $backend_pid 2>/dev/null || kill -9 $backend_pid 2>/dev/null
        sleep 1
    fi

    # Kill processes on frontend port
    local frontend_pid=$(lsof -ti:$FRONTEND_PORT 2>/dev/null)
    if [ -n "$frontend_pid" ]; then
        echo -e "  Stopping frontend (PID: $frontend_pid)..."
        kill $frontend_pid 2>/dev/null || kill -9 $frontend_pid 2>/dev/null
        sleep 1
    fi

    echo -e "  ${GREEN}✓ Ports cleared${NC}"
    echo ""
}

# Log file
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

echo -e "${BLUE}╔═══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Style Refine Agent               ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════╝${NC}"
echo ""

# Check for required tools
check_requirements() {
    echo -e "${CYAN}[1/4] Checking requirements...${NC}"

    local missing=0

    if ! command -v python3 &> /dev/null; then
        echo -e "  ${RED}✗ python3 not found${NC}"
        missing=1
    else
        echo -e "  ${GREEN}✓ python3 $(python3 --version 2>&1 | cut -d' ' -f2)${NC}"
    fi

    if ! command -v npm &> /dev/null; then
        echo -e "  ${RED}✗ npm not found${NC}"
        missing=1
    else
        echo -e "  ${GREEN}✓ npm $(npm --version)${NC}"
    fi

    if ! command -v ollama &> /dev/null; then
        echo -e "  ${YELLOW}! ollama CLI not in PATH (may still work via API)${NC}"
    else
        echo -e "  ${GREEN}✓ ollama installed${NC}"
    fi

    if [ $missing -eq 1 ]; then
        echo -e "\n${RED}Missing required tools. Please install them and try again.${NC}"
        exit 1
    fi
    echo ""
}

# Setup Python virtual environment
setup_backend() {
    echo -e "${CYAN}[2/4] Setting up backend...${NC}"

    if [ ! -d "venv" ]; then
        echo -e "  Creating virtual environment..."
        python3 -m venv venv
    else
        echo -e "  ${GREEN}✓ Virtual environment exists${NC}"
    fi

    source venv/bin/activate

    echo -e "  Installing Python dependencies..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt

    mkdir -p outputs
    echo -e "  ${GREEN}✓ Backend ready${NC}"
    echo ""
}

# Setup frontend
setup_frontend() {
    echo -e "${CYAN}[3/4] Setting up frontend...${NC}"

    cd frontend

    if [ ! -d "node_modules" ]; then
        echo -e "  Installing npm dependencies..."
        npm install --silent 2>/dev/null || npm install
    else
        echo -e "  ${GREEN}✓ Node modules exist${NC}"
    fi

    cd ..
    echo -e "  ${GREEN}✓ Frontend ready${NC}"
    echo ""
}

# Check external services
check_services() {
    echo -e "${CYAN}[4/4] Checking external services...${NC}"

    # Load env vars
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    fi

    OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
    COMFYUI_URL="${COMFYUI_URL:-http://localhost:8188}"
    VLM_MODEL="${VLM_MODEL:-llama3.2-vision:11b}"

    # Check Ollama
    echo -e "  Ollama (${OLLAMA_URL})..."
    if curl -s --connect-timeout 5 "${OLLAMA_URL}/api/tags" > /dev/null 2>&1; then
        echo -e "    ${GREEN}✓ Connected${NC}"

        # Check model
        MODELS=$(curl -s "${OLLAMA_URL}/api/tags" | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
        if echo "$MODELS" | grep -q "$VLM_MODEL"; then
            echo -e "    ${GREEN}✓ Model '${VLM_MODEL}' available${NC}"
        else
            echo -e "    ${RED}✗ Model '${VLM_MODEL}' NOT FOUND${NC}"
            echo -e "    ${YELLOW}  Available models:${NC}"
            echo "$MODELS" | while read -r model; do
                echo -e "      - $model"
            done
            echo -e "    ${YELLOW}  Run: ollama pull ${VLM_MODEL}${NC}"
        fi
    else
        echo -e "    ${RED}✗ Not connected${NC}"
        echo -e "    ${YELLOW}  Start with: ollama serve${NC}"
    fi

    # Check ComfyUI
    echo -e "  ComfyUI (${COMFYUI_URL})..."
    if curl -s --connect-timeout 5 "${COMFYUI_URL}/system_stats" > /dev/null 2>&1; then
        echo -e "    ${GREEN}✓ Connected${NC}"
    else
        echo -e "    ${RED}✗ Not connected${NC}"
        echo -e "    ${YELLOW}  Make sure ComfyUI is running${NC}"
    fi

    echo ""
}

# Run backend only
run_backend() {
    stop_services
    echo -e "${BLUE}Starting backend on http://localhost:${BACKEND_PORT}${NC}"
    echo -e "${YELLOW}Logs: ${BACKEND_LOG}${NC}"
    echo ""
    source venv/bin/activate
    cd "$PROJECT_DIR"

    # Run with output to both console and log file
    python -m uvicorn backend.main:app \
        --host 0.0.0.0 \
        --port $BACKEND_PORT \
        --reload \
        --log-level info 2>&1 | tee "$BACKEND_LOG"
}

# Run frontend only
run_frontend() {
    stop_services
    echo -e "${BLUE}Starting frontend on http://localhost:${FRONTEND_PORT}${NC}"
    echo -e "${YELLOW}Logs: ${FRONTEND_LOG}${NC}"
    echo ""
    cd "$PROJECT_DIR/frontend"
    npm run dev 2>&1 | tee "$FRONTEND_LOG"
}

# Run both in parallel
run_all() {
    stop_services
    echo -e "${BLUE}Starting services...${NC}"
    echo -e "  Backend log:  ${BACKEND_LOG}"
    echo -e "  Frontend log: ${FRONTEND_LOG}"
    echo ""

    # Clear old logs
    > "$BACKEND_LOG"
    > "$FRONTEND_LOG"

    # Start backend in background
    source venv/bin/activate
    cd "$PROJECT_DIR"
    python -m uvicorn backend.main:app \
        --host 0.0.0.0 \
        --port $BACKEND_PORT \
        --reload \
        --log-level info >> "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!

    # Give backend a moment to start
    echo -e "  Waiting for backend to start..."
    sleep 3

    # Check if backend started
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}Backend failed to start! Check ${BACKEND_LOG}${NC}"
        echo -e "${YELLOW}Last 20 lines of log:${NC}"
        tail -20 "$BACKEND_LOG"
        exit 1
    fi

    # Start frontend in background
    cd "$PROJECT_DIR/frontend"
    npm run dev >> "$FRONTEND_LOG" 2>&1 &
    FRONTEND_PID=$!

    sleep 2

    # Check if frontend started
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}Frontend failed to start! Check ${FRONTEND_LOG}${NC}"
        tail -20 "$FRONTEND_LOG"
        kill $BACKEND_PID 2>/dev/null
        exit 1
    fi

    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  Services running!                    ║${NC}"
    echo -e "${GREEN}╠═══════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  Frontend: http://localhost:${FRONTEND_PORT}      ║${NC}"
    echo -e "${GREEN}║  Backend:  http://localhost:${BACKEND_PORT}      ║${NC}"
    echo -e "${GREEN}║  API Docs: http://localhost:${BACKEND_PORT}/docs ║${NC}"
    echo -e "${GREEN}║  Health:   http://localhost:${BACKEND_PORT}/health${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
    echo -e "${CYAN}Tip: Run 'tail -f logs/backend.log' in another terminal for live logs${NC}"
    echo ""

    # Handle Ctrl+C
    trap 'echo -e "\n${RED}Stopping services...${NC}"; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0' SIGINT SIGTERM

    # Monitor processes
    while true; do
        if ! kill -0 $BACKEND_PID 2>/dev/null; then
            echo -e "${RED}Backend crashed! Check ${BACKEND_LOG}${NC}"
            tail -30 "$BACKEND_LOG"
            kill $FRONTEND_PID 2>/dev/null
            exit 1
        fi
        if ! kill -0 $FRONTEND_PID 2>/dev/null; then
            echo -e "${RED}Frontend crashed! Check ${FRONTEND_LOG}${NC}"
            tail -30 "$FRONTEND_LOG"
            kill $BACKEND_PID 2>/dev/null
            exit 1
        fi
        sleep 5
    done
}

# Show logs
show_logs() {
    if [ "$1" == "backend" ]; then
        tail -f "$BACKEND_LOG"
    elif [ "$1" == "frontend" ]; then
        tail -f "$FRONTEND_LOG"
    else
        echo -e "${CYAN}Showing both logs (backend=blue, frontend=green)${NC}"
        tail -f "$BACKEND_LOG" | sed "s/^/[backend] /" &
        tail -f "$FRONTEND_LOG" | sed "s/^/[frontend] /"
    fi
}

# Main
case "${1:-}" in
    setup)
        check_requirements
        setup_backend
        setup_frontend
        check_services
        echo -e "${GREEN}Setup complete! Run './run.sh' to start.${NC}"
        ;;
    backend)
        run_backend
        ;;
    frontend)
        run_frontend
        ;;
    stop)
        stop_services
        echo -e "${GREEN}Services stopped.${NC}"
        ;;
    check)
        check_services
        ;;
    logs)
        show_logs "$2"
        ;;
    *)
        check_requirements
        setup_backend
        setup_frontend
        check_services
        run_all
        ;;
esac
