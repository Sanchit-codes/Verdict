#!/bin/bash
set -e

echo "🚀 Starting HallucinationGuard Full Stack..."
echo ""

# Kill any existing processes on ports 5000, 3000
echo "Checking for existing processes..."
lsof -ti:5000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

# Start Flask server
echo "📦 Starting Flask API server (port 5000)..."
cd server
PORT=5000 CORS_ORIGIN=http://localhost:3000 python3 run.py > /tmp/flask_server.log 2>&1 &
FLASK_PID=$!
echo "Flask PID: $FLASK_PID"
cd ..

# Wait for Flask to be ready
echo "⏳ Waiting for Flask server to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "✓ Flask server ready!"
    break
  fi
  echo "  Attempt $i/30..."
  sleep 1
done

# Start Next.js frontend
echo ""
echo "🎨 Starting Next.js frontend (port 3000)..."
cd GuardlyFrontend
npm run dev > /tmp/nextjs_frontend.log 2>&1 &
NEXTJS_PID=$!
echo "Next.js PID: $NEXTJS_PID"
cd ..

# Wait for Next.js to be ready
echo "⏳ Waiting for Next.js to be ready..."
for i in {1..30}; do
  if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "✓ Next.js frontend ready!"
    break
  fi
  echo "  Attempt $i/30..."
  sleep 1
done

# Final status check
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ All services started successfully!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📍 Services Running:"
echo "  • Flask API:     http://localhost:5000"
echo "  • Next.js UI:    http://localhost:3000"
echo "  • API Health:    http://localhost:5000/api/health"
echo ""
echo "📋 View Logs:"
echo "  • Flask:  tail -f /tmp/flask_server.log"
echo "  • Next.js: tail -f /tmp/nextjs_frontend.log"
echo ""
echo "🛑 To stop services:"
echo "  • Press Ctrl+C here or kill $FLASK_PID and $NEXTJS_PID"
echo ""

# Wait for user to stop
wait
