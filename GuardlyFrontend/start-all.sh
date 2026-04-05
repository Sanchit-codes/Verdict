#!/bin/bash

##############################################################################
# HallucinationGuard Startup Script
#
# Starts both Flask backend and Next.js frontend services with health checks
# and displays a status report.
#
# Usage:
#   ./start-all.sh
#
# The script will:
#   1. Start Flask backend on port 5000 (background)
#   2. Start Next.js frontend on port 3000 (background)
#   3. Wait for both services to be ready (up to 30 retries, 1s each)
#   4. Display status and instructions
#   5. Clean up on exit (Ctrl+C kills both services)
##############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_HOST="localhost"
BACKEND_PORT="5000"
FRONTEND_HOST="localhost"
FRONTEND_PORT="3000"
MAX_RETRIES=30
RETRY_INTERVAL=1

# Store PIDs of background processes for cleanup
BACKEND_PID=""
FRONTEND_PID=""

##############################################################################
# Cleanup Function - Kill background processes on exit
##############################################################################
cleanup() {
    echo ""
    echo -e "${YELLOW}→${NC} Shutting down services..."
    
    if [ -n "$BACKEND_PID" ]; then
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            echo "  Stopping backend (PID: $BACKEND_PID)..."
            kill "$BACKEND_PID" 2>/dev/null || true
        fi
    fi
    
    if [ -n "$FRONTEND_PID" ]; then
        if kill -0 "$FRONTEND_PID" 2>/dev/null; then
            echo "  Stopping frontend (PID: $FRONTEND_PID)..."
            kill "$FRONTEND_PID" 2>/dev/null || true
        fi
    fi
    
    # Wait for processes to terminate gracefully (max 5 seconds)
    for i in {1..5}; do
        if ([ -z "$BACKEND_PID" ] || ! kill -0 "$BACKEND_PID" 2>/dev/null) && \
           ([ -z "$FRONTEND_PID" ] || ! kill -0 "$FRONTEND_PID" 2>/dev/null); then
            break
        fi
        sleep 1
    done
    
    # Force kill if still running
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "  Force stopping backend..."
        kill -9 "$BACKEND_PID" 2>/dev/null || true
    fi
    
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "  Force stopping frontend..."
        kill -9 "$FRONTEND_PID" 2>/dev/null || true
    fi
    
    echo -e "${GREEN}✓${NC} Services stopped"
    exit 0
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

##############################################################################
# Health Check Function
##############################################################################
check_health() {
    local service="$1"
    local url="$2"
    local max_retries="$3"
    
    echo "  Checking $service..."
    
    for i in $(seq 1 "$max_retries"); do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} $service responded"
            return 0
        fi
        
        if [ "$i" -lt "$max_retries" ]; then
            echo -n "."
            sleep "$RETRY_INTERVAL"
        fi
    done
    
    echo ""
    echo -e "  ${RED}✗${NC} $service failed to respond after ${max_retries}s"
    return 1
}

##############################################################################
# Main Script
##############################################################################

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  HallucinationGuard - Starting Services...               ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${YELLOW}→${NC} Project root: $PROJECT_ROOT"
echo ""

##############################################################################
# Start Backend
##############################################################################
echo -e "${YELLOW}→${NC} Starting Flask backend on port $BACKEND_PORT..."

cd "$PROJECT_ROOT"

# Check if port is already in use
if lsof -Pi ":$BACKEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Port $BACKEND_PORT is already in use. Stop the service using that port and try again."
    echo "  Hint: lsof -i :$BACKEND_PORT"
    exit 1
fi

PORT=$BACKEND_PORT python server/run.py > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo "  Backend process started (PID: $BACKEND_PID)"
sleep 1

# Check if backend process is still running
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo -e "${RED}✗${NC} Backend failed to start. Check /tmp/backend.log for details:"
    echo "---"
    cat /tmp/backend.log
    echo "---"
    exit 1
fi

##############################################################################
# Start Frontend
##############################################################################
echo -e "${YELLOW}→${NC} Starting Next.js frontend on port $FRONTEND_PORT..."

cd "$SCRIPT_DIR"

# Check if port is already in use
if lsof -Pi ":$FRONTEND_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Port $FRONTEND_PORT is already in use. Stop the service using that port and try again."
    echo "  Hint: lsof -i :$FRONTEND_PORT"
    exit 1
fi

npm run dev > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  Frontend process started (PID: $FRONTEND_PID)"
sleep 2

# Check if frontend process is still running
if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo -e "${RED}✗${NC} Frontend failed to start. Check /tmp/frontend.log for details:"
    echo "---"
    tail -20 /tmp/frontend.log
    echo "---"
    exit 1
fi

##############################################################################
# Health Checks
##############################################################################
echo ""
echo -e "${YELLOW}→${NC} Waiting for services to be ready (max ${MAX_RETRIES}s)..."
echo ""

# Check backend health
if check_health "Backend" "http://$BACKEND_HOST:$BACKEND_PORT/api/health" "$MAX_RETRIES"; then
    BACKEND_READY=1
else
    BACKEND_READY=0
fi

echo ""

# Check frontend health
if check_health "Frontend" "http://$FRONTEND_HOST:$FRONTEND_PORT" "$MAX_RETRIES"; then
    FRONTEND_READY=1
else
    FRONTEND_READY=0
fi

##############################################################################
# Status Report
##############################################################################
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  Service Status                                          ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$BACKEND_READY" -eq 1 ]; then
    echo -e "${GREEN}✓${NC} Backend ready at http://$BACKEND_HOST:$BACKEND_PORT"
    echo "  API Docs: http://$BACKEND_HOST:$BACKEND_PORT/api/docs"
else
    echo -e "${RED}✗${NC} Backend failed to start"
fi

if [ "$FRONTEND_READY" -eq 1 ]; then
    echo -e "${GREEN}✓${NC} Frontend ready at http://$FRONTEND_HOST:$FRONTEND_PORT"
else
    echo -e "${RED}✗${NC} Frontend failed to start"
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  Next Steps                                              ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$BACKEND_READY" -eq 1 ] && [ "$FRONTEND_READY" -eq 1 ]; then
    echo -e "${YELLOW}→${NC} Open your browser:"
    echo -e "    ${BLUE}http://$FRONTEND_HOST:$FRONTEND_PORT${NC}"
    echo ""
    echo -e "${YELLOW}→${NC} Backend API docs:"
    echo -e "    ${BLUE}http://$BACKEND_HOST:$BACKEND_PORT/api/docs${NC}"
    echo ""
else
    echo -e "${YELLOW}→${NC} Some services failed to start."
    echo -e "${YELLOW}→${NC} Backend log: /tmp/backend.log"
    echo -e "${YELLOW}→${NC} Frontend log: /tmp/frontend.log"
    echo ""
fi

echo -e "${YELLOW}→${NC} Press ${BLUE}Ctrl+C${NC} to stop all services"
echo ""

##############################################################################
# Keep Script Running
##############################################################################

# Wait for either process to exit
while kill -0 "$BACKEND_PID" 2>/dev/null || kill -0 "$FRONTEND_PID" 2>/dev/null; do
    sleep 1
done
