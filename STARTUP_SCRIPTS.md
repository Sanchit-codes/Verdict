# Startup Scripts & Health Check Tools

This directory contains utilities for starting, stopping, and monitoring the HallucinationGuard full stack (Flask backend + Next.js frontend).

## Quick Start

```bash
# Start everything
./start-all.sh

# In another terminal, check health
./check-health.sh

# Stop everything
./stop-all.sh
```

## Files

### `start-all.sh` (executable)
**Purpose:** Start both Flask API server and Next.js frontend in the background.

**What it does:**
1. Kills any existing processes on ports 5000 (Flask) and 3000 (Next.js)
2. Starts Flask server with `PORT=5000 CORS_ORIGIN=http://localhost:3000`
3. Waits for Flask to become ready (health check)
4. Starts Next.js frontend with `npm run dev`
5. Waits for Next.js to become ready
6. Displays service URLs and log file locations
7. Waits for user input (Ctrl+C to stop)

**Output:**
- Displays PIDs for both processes
- Shows service URLs:
  - Flask API: http://localhost:5000
  - Next.js UI: http://localhost:3000
  - Health endpoint: http://localhost:5000/api/health
- Shows log file paths for debugging

**Logs:**
- Flask: `/tmp/flask_server.log`
- Next.js: `/tmp/nextjs_frontend.log`

### `stop-all.sh` (executable)
**Purpose:** Stop all running services (Flask + Next.js).

**What it does:**
1. Kills processes on port 5000 (Flask)
2. Kills processes on port 3000 (Next.js)
3. Confirms termination

**Usage:**
```bash
./stop-all.sh
```

### `check-health.sh` (executable)
**Purpose:** Check if both services are running and responding.

**What it does:**
1. Calls Flask health endpoint (`http://localhost:5000/api/health`)
2. Checks if Next.js frontend responds to HTTP request
3. Displays results with indicators (✓ or ❌)

**Usage:**
```bash
./check-health.sh
```

**Example output:**
```
Checking service health...

Flask API:
{
  "status": "healthy",
  "timestamp": "2024-04-05T08:00:00Z",
  "version": "0.1.0"
}

Next.js:
✓ Responding
```

## Configuration

### Frontend Environment Variables

The `.env.local` file in `GuardlyFrontend/` contains:
```
NEXT_PUBLIC_GUARDLY_API=http://localhost:5000/api
NEXT_PUBLIC_GUARDLY_POLICY=default
```

**Note:** `.env.local` is gitignored for security. It's created automatically by the startup script. To customize:
```bash
# Edit the file
nano GuardlyFrontend/.env.local

# Change API endpoint or policy as needed
# Then restart services
./stop-all.sh
./start-all.sh
```

### Flask Environment Variables

Set these before running `./start-all.sh`:
```bash
# Port (default: 5000)
export PORT=5000

# CORS origin (default: http://localhost:3000)
export CORS_ORIGIN=http://localhost:3000

# Flask environment (default: development)
export FLASK_ENV=development

# Disable specific models (e.g., for faster startup)
export HG_DISABLE_HHEM=false

# Then run
./start-all.sh
```

## Troubleshooting

### Services don't start
```bash
# Check if ports are already in use
lsof -i:5000
lsof -i:3000

# If ports are in use, kill the existing processes
lsof -ti:5000 | xargs kill -9
lsof -ti:3000 | xargs kill -9

# Then try again
./start-all.sh
```

### Flask server won't start
```bash
# Check Flask manually
cd server
PORT=5000 CORS_ORIGIN=http://localhost:3000 python3 run.py

# Look for error messages
# Press Ctrl+C when done
```

### Next.js won't start
```bash
# Check dependencies are installed
cd GuardlyFrontend
npm install

# Try starting manually
npm run dev

# Look for error messages
# Press Ctrl+C when done
```

### Health check shows errors
```bash
# View Flask logs
tail -50 /tmp/flask_server.log

# View Next.js logs
tail -50 /tmp/nextjs_frontend.log

# Or follow logs in real-time
tail -f /tmp/flask_server.log
```

### Can't connect to API from frontend
```bash
# Verify .env.local is set correctly
cat GuardlyFrontend/.env.local

# Should show: NEXT_PUBLIC_GUARDLY_API=http://localhost:5000/api

# Check CORS headers are correct
curl -H "Origin: http://localhost:3000" -v http://localhost:5000/api/health

# Response should include: Access-Control-Allow-Origin: http://localhost:3000
```

## Integration Testing

See `INTEGRATION_TEST.md` for comprehensive manual testing steps covering:
- Service startup and health checks
- Chat message validation
- Error handling
- CORS configuration
- Performance validation
- Debugging checklist

## Advanced Usage

### Run services in separate terminals (for development)

**Terminal 1 - Flask:**
```bash
cd server
PORT=5000 CORS_ORIGIN=http://localhost:3000 python3 run.py
```

**Terminal 2 - Next.js:**
```bash
cd GuardlyFrontend
npm run dev
```

### Custom ports

Change the port in `start-all.sh` (search for `5000` or `3000`) or set environment variables:

```bash
# Before running start-all.sh
export PORT=8000
export FRONTEND_PORT=8080
# Edit start-all.sh to use these variables
# Or edit directly in the script

./start-all.sh
```

### Disable model preloading (faster startup)

```bash
export HG_DISABLE_HHEM=true
./start-all.sh
```

This will skip HHEM model loading and use only heuristics + embeddings validators.

### Enable debug logging

```bash
export HG_LOG_LEVEL=DEBUG
./start-all.sh

# Or for Flask specifically
export FLASK_ENV=development
export FLASK_DEBUG=1
./start-all.sh
```

## Performance Targets

- **Flask startup:** < 30 seconds (including model loading)
- **Next.js startup:** < 30 seconds
- **Health check response:** < 100ms
- **Validation latency (p95):** < 100ms
- **UI responsiveness:** Immediate feedback to user input

Monitor these via `check-health.sh` and browser DevTools Network tab.

## CI/CD Integration

For automated startup verification in CI pipelines:

```bash
#!/bin/bash
set -e

# Start services
./start-all.sh &
START_PID=$!

# Wait for services
sleep 5

# Run health check
./check-health.sh || exit 1

# Stop services
./stop-all.sh

# Exit with success
wait $START_PID
exit 0
```

## Notes

- Scripts are POSIX-compliant (macOS/Linux)
- Windows users can use Git Bash or WSL
- All logs go to `/tmp/` for easy access
- Services run in background; use `ps aux | grep -E "python|node"` to see running processes
- Ctrl+C when running `start-all.sh` will terminate the wait loop but not kill the services (use `stop-all.sh` to cleanly stop)
