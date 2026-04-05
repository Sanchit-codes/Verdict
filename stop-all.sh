#!/bin/bash
echo "🛑 Stopping all services..."
lsof -ti:5000 | xargs kill -9 2>/dev/null || echo "  Flask not running"
lsof -ti:3000 | xargs kill -9 2>/dev/null || echo "  Next.js not running"
echo "✓ All services stopped"
