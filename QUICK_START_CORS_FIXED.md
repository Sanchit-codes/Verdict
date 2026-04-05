# GuardlyAI Quick Start — CORS Fixed ✅

## Prerequisites
- Python 3.10+
- Node.js 18+
- Virtual environment created: `python -m venv venv`
- Dependencies installed: `pip install -e ".[gemini,dev]"` and `cd GuardlyFrontend && npm install`

## Start Backend & Frontend (Production-Ready)

### Option 1: Two Terminal Windows (Recommended)

**Terminal 1 — Backend API on port 5500**
```bash
source venv/bin/activate
PORT=5500 CORS_ORIGIN=http://localhost:3000 python server/run.py
```

Expected output:
```
🚀 Starting HallucinationGuard API Server
   Listening on 0.0.0.0:5500
   CORS Origin: http://localhost:3000
   Health: http://0.0.0.0:5500/api/health
```

**Terminal 2 — Frontend on port 3000**
```bash
cd GuardlyFrontend
npm run dev
```

Expected output:
```
> next dev
- ready started server on 0.0.0.0:3000, url: http://localhost:3000
```

### Option 2: Single Terminal with Background Processes

```bash
# Backend
source venv/bin/activate
PORT=5500 CORS_ORIGIN=http://localhost:3000 python server/run.py &

# Frontend (in same terminal)
cd GuardlyFrontend
npm run dev
```

## Verify Everything Works

### ✓ Backend Health
```bash
curl http://localhost:5500/api/health
```

Response:
```json
{
  "status": "healthy",
  "guard_available": true,
  "models_loaded": {
    "embedding": true,
    "heuristics": true,
    "hhem": true
  }
}
```

### ✓ CORS Headers
```bash
curl -I -X OPTIONS -H "Origin: http://localhost:3000" http://localhost:5500/api/health | grep -i access-control
```

Response should include:
```
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With
Access-Control-Allow-Credentials: true
```

### ✓ Frontend Access
Open browser: http://localhost:3000

Should load without CORS errors.

## Using the System

### Validate Text
```bash
curl -X POST http://localhost:5500/api/validate \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:3000" \
  -d '{
    "prompt": "What is the capital of France?",
    "output": "The capital of France is Paris.",
    "context": "France is a country in Europe. Its capital is Paris.",
    "policy": "default"
  }'
```

### Generate + Validate (with Gemini)
Requires `GOOGLE_API_KEY` environment variable:

```bash
export GOOGLE_API_KEY=your_api_key_here

curl -X POST http://localhost:5500/api/generate \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:3000" \
  -d '{
    "prompt": "Summarize the theory of relativity",
    "context": "Einstein developed the theory of general relativity in 1916...",
    "policy": "default"
  }'
```

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | 5000 | Backend API port |
| `CORS_ORIGIN` | http://localhost:3000 | Frontend URL (for CORS) |
| `GOOGLE_API_KEY` | — | Gemini API key (required for /generate) |
| `HG_DEFAULT_POLICY` | default | Validation policy to use |
| `HG_LOG_LEVEL` | INFO | Logging level (DEBUG, INFO, WARNING) |

### Available Policies

- `default` — Balanced for general use
- `rag_strict` — Strict for healthcare/finance (requires context)
- `chatbot` — Fast for interactive chat

## Troubleshooting

### CORS Errors
**Error**: "Cross-Origin Request Blocked"

**Solution**:
1. Verify `PORT=5500` set when starting backend
2. Verify `CORS_ORIGIN=http://localhost:3000` set
3. Check frontend `.env.local` has `NEXT_PUBLIC_GUARDLY_API=http://localhost:5500/api`
4. Restart both services

### Port Already in Use
```bash
# Kill process on port 5500
lsof -i :5500 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Kill process on port 3000
lsof -i :3000 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

### Models Not Loading
**Solution**: First run takes 1-2 minutes to download models. Wait for console to show "Model preload complete".

## Architecture

```
User Browser (http://localhost:3000)
         ↓
   Next.js Frontend
         ↓
  [CORS Preflight: OPTIONS]
         ↓
Flask Backend (http://localhost:5500)
    ↓        ↓        ↓
  Heuristics Embedding HHEM
```

## Monitoring

### Backend Logs
Look for:
- `✓ Guard initialized successfully`
- `[Warmup] Model preload complete`
- Request logs with latency: `latency=XXms`

### Frontend Console (DevTools)
Look for:
- Network requests to `http://localhost:5500/api/*`
- No CORS errors (preflight should succeed)
- Response status 200 OK

## Next Steps

1. **Try validation** on frontend (http://localhost:3000)
2. **Test Gemini integration** (requires API key)
3. **Adjust policies** in `policies/` directory
4. **Review logs** for performance insights
5. **Deploy** to production with proper environment variables

---

✅ **System Ready!** Both backend and frontend are configured with proper CORS headers.

For more details, see:
- `CORS_RESOLUTION_SUMMARY.md` — Technical deep dive
- `GEMINI_SETUP.md` — Gemini API setup
- `API_REFERENCE.md` — Full API documentation
- `README.md` — Project overview
