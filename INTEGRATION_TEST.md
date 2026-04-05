# Integration Testing Guide for HallucinationGuard Full Stack

This guide provides manual integration testing steps to verify that both the Flask backend and Next.js frontend work together correctly.

## Prerequisites

- Both services are running via `./start-all.sh`
- No error messages in `/tmp/flask_server.log` or `/tmp/nextjs_frontend.log`
- Ports 5000 (Flask) and 3000 (Next.js) are available

## Quick Health Check

```bash
./check-health.sh
```

Should show:
- Flask API responds with status JSON
- Next.js returns HTML response

---

## Manual Integration Tests

### Test 1: Basic Service Startup ✓

**Steps:**
1. Terminal 1: Run `./start-all.sh`
2. Wait for "All services started successfully" message
3. Verify both PIDs are displayed

**Expected Result:**
- Flask API starts on port 5000
- Next.js frontend starts on port 3000
- Both services reach ready state within 30 seconds
- No errors in startup logs

**Validation:**
```bash
# In another terminal
ps aux | grep -E "python|node" | grep -v grep
```

Should show both Flask and Next.js processes running.

---

### Test 2: API Health Endpoint ✓

**Steps:**
1. Open terminal
2. Run: `curl http://localhost:5000/api/health`

**Expected Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-04-05T08:00:00Z",
  "version": "0.1.0",
  "environment": "development",
  "models_loaded": true
}
```

**What to Check:**
- Status is "healthy"
- Timestamp is recent
- Models are loaded (models_loaded: true)

---

### Test 3: Frontend Loads Successfully ✓

**Steps:**
1. Open browser: `http://localhost:3000`
2. Wait for page to fully load (check console for errors)
3. Verify you see the main chat interface

**What to Check:**
- Page loads without 404 errors
- CSS is styled (Tailwind is working)
- Input field is visible
- "Settings" button is visible (if implemented)
- No red error messages in browser console

**Browser Console Check:**
1. Open DevTools (F12 / Cmd+Option+I)
2. Go to Console tab
3. Should show no errors (warnings are OK)
4. Should show API connection attempt logs

---

### Test 4: Chat Message Validation ✓

**Steps:**
1. In browser at `http://localhost:3000`
2. Type a message: `"The capital of France is London"`
3. Click send or press Enter
4. Wait for response

**What to Check:**
- Message appears in chat history
- API request is sent to Flask backend
- Validation decision appears (Allow/Block/Regenerate/Abstain)
- Risk score is displayed (0.0 - 1.0)
- Evidence text explains the decision

**Browser Network Tab:**
1. Open DevTools → Network tab
2. Send a message
3. Look for POST request to `http://localhost:5000/api/validate`
4. Response should include:
   ```json
   {
     "decision": "block|allow|regenerate|abstain",
     "risk_score": 0.85,
     "evidence": "...",
     "validation_latency_ms": 45
   }
   ```

**Flask Server Logs:**
```bash
tail -f /tmp/flask_server.log
```

Should show:
```
POST /api/validate - 200 OK
Validation completed in 45ms
```

---

### Test 5: Faithful Output (Should Allow) ✓

**Steps:**
1. Type: `"The capital of France is Paris"`
2. Include context: The system should have context about France/Paris
3. Send message

**Expected Result:**
- Decision: "allow"
- Risk score: Low (0.0 - 0.3)
- Evidence: References high context overlap or faithful content

---

### Test 6: Hallucinated Output (Should Block) ✓

**Steps:**
1. Type: `"The capital of France is Tokyo and it has 50 million people"`
2. Send message

**Expected Result:**
- Decision: "block"
- Risk score: High (0.7 - 1.0)
- Evidence: References low context overlap or hallucination detected

---

### Test 7: API Endpoint Testing ✓

**Manual API Test with curl:**

```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "output": "The capital of France is Paris.",
    "context": "France is a country in Western Europe. Its capital is Paris."
  }'
```

**Expected Response:**
```json
{
  "id": "val-xyz123",
  "decision": "allow",
  "risk_score": 0.15,
  "evidence": "Output aligns well with provided context",
  "suggested_fix": null,
  "validation_latency_ms": 42,
  "timestamp": "2024-04-05T08:00:00Z"
}
```

---

### Test 8: Settings Page (if implemented) ✓

**Steps:**
1. Click "Settings" button (if present)
2. Verify you can see:
   - Current API endpoint
   - Current policy (default, rag_strict, chatbot)
3. Try changing the API endpoint
4. Try changing the policy
5. Send a message to verify new settings are used

**Expected Result:**
- Settings persist across messages
- Messages use the selected policy for validation
- No errors when changing settings

---

### Test 9: Error Handling - Backend Offline ✓

**Steps:**
1. Run `./check-health.sh` to verify everything is running
2. Run `./stop-all.sh` to stop Flask server only
3. Try to send a message in the frontend
4. Observe the error handling

**Expected Result:**
- Frontend shows connection error message
- Message appears in chat with error state
- No unhandled JavaScript errors
- User can see clear error message (e.g., "API unreachable")

**How to Stop Only Flask:**
```bash
lsof -ti:5000 | xargs kill -9
```

Then restart:
```bash
cd server && PORT=5000 CORS_ORIGIN=http://localhost:3000 python3 run.py &
```

---

### Test 10: Error Handling - CORS ✓

**Steps:**
1. Open browser DevTools (Network tab)
2. Send a message
3. Check for CORS errors

**Expected Result:**
- No CORS errors in browser
- API requests complete successfully
- Response headers include:
  - `Access-Control-Allow-Origin: http://localhost:3000`
  - `Access-Control-Allow-Methods: GET, POST, OPTIONS`

**If CORS errors appear:**
```bash
# Verify CORS_ORIGIN is set correctly
echo $CORS_ORIGIN  # Should be http://localhost:3000
```

---

### Test 11: Long Message Handling ✓

**Steps:**
1. Type a very long message (500+ characters)
2. Send it

**Expected Result:**
- Message is sent successfully
- No truncation
- Validation completes normally
- Response includes proper decision

---

### Test 12: Rapid Successive Messages ✓

**Steps:**
1. Send 5 messages in quick succession (without waiting for responses)
2. Observe the chat history

**Expected Result:**
- All messages are queued and processed
- Messages appear in order
- No skipped messages
- No rate limiting errors (unless implemented)

---

## Debugging Checklist

### If Flask Doesn't Start:
```bash
# Check if port 5000 is already in use
lsof -ti:5000

# Check Python installation
python3 --version

# Check Flask server manually
cd server
python3 run.py
# Look for error messages
```

### If Next.js Doesn't Start:
```bash
# Check if port 3000 is already in use
lsof -ti:3000

# Check Node/npm installation
node --version
npm --version

# Check dependencies
cd GuardlyFrontend
npm install

# Run manually
npm run dev
```

### If Services Start But Health Check Fails:
```bash
# Check Flask
curl -v http://localhost:5000/api/health

# Check Next.js
curl -v http://localhost:3000

# Check logs
tail -20 /tmp/flask_server.log
tail -20 /tmp/nextjs_frontend.log
```

### If Frontend Can't Connect to Backend:
1. Check `.env.local` has correct API URL:
   ```bash
   cat GuardlyFrontend/.env.local
   # Should show: NEXT_PUBLIC_GUARDLY_API=http://localhost:5000/api
   ```

2. Check CORS headers:
   ```bash
   curl -H "Origin: http://localhost:3000" -v http://localhost:5000/api/health
   ```

3. Verify Flask CORS_ORIGIN:
   ```bash
   grep "CORS_ORIGIN" /tmp/flask_server.log
   ```

---

## Performance Validation

### Response Latency Check:
1. Send a message
2. Check DevTools Network tab for `/api/validate` request
3. Verify latency is < 200ms (p95 < 100ms target)

### Frontend Responsiveness:
1. Observe UI responsiveness while waiting for API response
2. Should not freeze or become unresponsive
3. Loading indicator should be visible (if implemented)

---

## Summary Checklist

- [ ] `./start-all.sh` runs without errors
- [ ] Both services reach ready state
- [ ] Health check returns success for both
- [ ] Frontend loads at http://localhost:3000
- [ ] Chat input field works
- [ ] Messages are sent to backend
- [ ] Validation decisions appear in UI
- [ ] Risk scores are displayed
- [ ] Evidence text is informative
- [ ] API latency is acceptable (<200ms)
- [ ] No CORS errors in browser console
- [ ] Backend logs show successful requests
- [ ] Error handling works when services are offline
- [ ] Settings can be changed (if implemented)
- [ ] Multiple rapid messages are handled correctly

---

## Continuous Integration Testing (Future)

Once these manual tests pass, consider automating with:
- Playwright/Cypress for frontend e2e tests
- pytest for backend integration tests
- Health check in CI pipeline before deployment
