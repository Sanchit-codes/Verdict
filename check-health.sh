#!/bin/bash
echo "Checking service health..."
echo ""
echo "Flask API:"
curl -s http://localhost:5000/api/health | jq . 2>/dev/null || echo "❌ Not responding or jq not available. Try: curl http://localhost:5000/api/health"
echo ""
echo "Next.js:"
curl -s http://localhost:3000 | grep -q "<html>" && echo "✓ Responding" || echo "❌ Not responding"
