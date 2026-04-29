# HallucinationGuard Flask API Backend

A production-ready Flask REST API that wraps the HallucinationGuard Python SDK, providing a standard HTTP interface for validating LLM outputs and enforcing intent with ArmorIQ.

## Quick Start

### Installation

```bash
# Install the project with all dependencies
pip install -e ".[dev]"

# Or if already installed, ensure Flask is available
pip install flask>=2.0.0
```

### Running the Server

```bash
# Default development mode (port 5000, debug enabled)
python server/run.py

# Or using Flask CLI
FLASK_APP=server:create_app flask run

# Production mode
FLASK_ENV=production python server/run.py

# Custom port
PORT=3000 python server/run.py

# With specific policy
HG_DEFAULT_POLICY=rag_strict python server/run.py
```

The server will start and display:
```
🚀 Starting HallucinationGuard API Server
   Version: 1.0.0
   Environment: DEVELOPMENT
   Policy: default
   Models preload: True
   Listening on 0.0.0.0:5000

   API Docs: http://0.0.0.0:5000/api/docs
   Health: http://0.0.0.0:5000/api/health
```

## API Endpoints

All endpoints use JSON request/response format with proper Content-Type headers.

### Base URL

```
http://localhost:5000/api
```

### 1. POST /api/validate

Validate a single model output for hallucinations.

**Request:**
```json
{
  "prompt": "What is the capital of France?",
  "output": "The capital of France is Paris.",
  "context": "France is a country in Western Europe. Its capital city is Paris.",
  "policy": "default",
  "domain": "geography"
}
```

**Response (200 OK):**
```json
{
  "decision": "allow",
  "risk_score": 0.15,
  "confidence": 0.92,
  "output": "The capital of France is Paris.",
  "evidence": "Output matches context with high cosine similarity (0.95).",
  "latency_ms": 48.5,
  "policy_name": "default",
  "prompt_injection_risk": 0.05,
  "tier_results": [
    {
      "validator_name": "heuristics",
      "score": 0.85,
      "passed": true,
      "evidence": "Entity overlap: 1.0",
      "latency_ms": 2.1
    },
    {
      "validator_name": "embedding",
      "score": 0.95,
      "passed": true,
      "evidence": "Cosine similarity: 0.95",
      "latency_ms": 15.3
    }
  ]
}
```

**Error Response (422 Unprocessable Entity):**
```json
{
  "error": "Invalid request: prompt is required",
  "code": "VALIDATION_ERROR",
  "details": {
    "field": "prompt",
    "reason": "min_length=1"
  }
}
```

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | Yes | — | User query that triggered generation |
| `output` | string | Yes | — | Model-generated text to validate |
| `context` | string | No | null | Reference context (e.g., retrieved documents) |
| `policy` | string | No | "default" | Policy name: `default`, `rag_strict`, `chatbot` |
| `domain` | string | No | "general" | Domain metadata: `healthcare`, `finance`, `legal`, etc. |
| `action_plan` | string | No | null | Optional action for ArmorIQ enforcement |
| `user_task` | string | No | null | Declared task scope for ArmorIQ |

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `decision` | string | Action: `allow`, `block`, `regenerate`, `abstain` |
| `risk_score` | float | Risk in [0.0, 1.0] where 1.0 = max risk |
| `confidence` | float | Confidence in [0.0, 1.0] based on validator agreement |
| `output` | string | The validated output (same as input) |
| `evidence` | string | Human-readable explanation |
| `suggested_fix` | string | Hint for regeneration (if `decision == "regenerate"`) |
| `latency_ms` | float | Total pipeline execution time |
| `policy_name` | string | Policy used for decision |
| `prompt_injection_risk` | float | Prompt injection risk in [0.0, 1.0] |
| `tier_results` | array | Individual validator results |
| `action_enforcement` | object | ArmorIQ result (if applicable) |

#### Examples with curl

**Faithful output (allow):**
```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is 2+2?",
    "output": "2+2 equals 4.",
    "context": "Basic arithmetic: 2+2=4"
  }'
```

**Hallucinated output (block):**
```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "output": "The capital of France is London.",
    "context": "France is a country in Europe. Its capital is Paris."
  }'
```

**With ArmorIQ enforcement:**
```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Search for flights to Paris",
    "output": "Found 5 flights available.",
    "context": "Available flights database...",
    "action_plan": "search_flights({\"destination\": \"Paris\"})",
    "user_task": "search for flights to Paris"
  }'
```

**Strict RAG policy:**
```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What medication should I take?",
    "output": "You should take aspirin.",
    "context": "Patient medical records...",
    "policy": "rag_strict",
    "domain": "healthcare"
  }'
```

### 2. GET /api/health

Health check endpoint to verify server and model availability.

**Request:**
```bash
curl http://localhost:5000/api/health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2024-04-05T12:34:56Z",
  "models_loaded": {
    "heuristics": true,
    "embedding": true,
    "hhem": true
  },
  "guard_available": true
}
```

**Degraded Response (503 Service Unavailable):**
```json
{
  "status": "degraded",
  "timestamp": "2024-04-05T12:34:56Z",
  "models_loaded": {
    "heuristics": false,
    "embedding": false,
    "hhem": false
  },
  "guard_available": false
}
```

#### Examples with curl

```bash
# Check health
curl http://localhost:5000/api/health | jq .

# Check with timeout (useful for monitoring)
curl --max-time 5 http://localhost:5000/api/health || echo "Unhealthy"
```

### 3. GET /api/version

Get version information for server and SDK.

**Request:**
```bash
curl http://localhost:5000/api/version
```

**Response (200 OK):**
```json
{
  "version": "1.0.0",
  "guard_version": "0.1.0",
  "python_version": "3.10.12"
}
```

#### Examples with curl

```bash
# Get version
curl http://localhost:5000/api/version | jq .

# Extract just the server version
curl -s http://localhost:5000/api/version | jq -r .version
```

### 4. POST /api/batch

Batch validate multiple outputs in a single request.

**Request:**
```json
{
  "validations": [
    {
      "prompt": "What is 2+2?",
      "output": "2+2 equals 4.",
      "context": "Basic arithmetic"
    },
    {
      "prompt": "What is the capital of France?",
      "output": "The capital is Paris.",
      "context": "France is in Europe with capital Paris",
      "policy": "rag_strict"
    }
  ],
  "max_parallel": 1
}
```

**Response (200 OK):**
```json
{
  "results": [
    {
      "decision": "allow",
      "risk_score": 0.1,
      "confidence": 0.95,
      "output": "2+2 equals 4.",
      "evidence": "Simple arithmetic, low hallucination risk.",
      "latency_ms": 35.2,
      "policy_name": "default",
      "prompt_injection_risk": 0.0
    },
    {
      "decision": "allow",
      "risk_score": 0.12,
      "confidence": 0.93,
      "output": "The capital is Paris.",
      "evidence": "Output matches context with high confidence.",
      "latency_ms": 42.1,
      "policy_name": "rag_strict",
      "prompt_injection_risk": 0.02
    }
  ],
  "total_time_ms": 150.5,
  "processed_count": 2,
  "failed_count": 0
}
```

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `validations` | array | Yes | — | Array of `ValidateRequest` objects |
| `max_parallel` | int | No | 1 | Max concurrent validations (1-10) |

#### Examples with curl

**Batch validation with 2 items:**
```bash
curl -X POST http://localhost:5000/api/batch \
  -H "Content-Type: application/json" \
  -d '{
    "validations": [
      {
        "prompt": "What is 2+2?",
        "output": "4",
        "context": "Arithmetic"
      },
      {
        "prompt": "What is the capital of France?",
        "output": "Paris",
        "context": "Geography: France..."
      }
    ],
    "max_parallel": 1
  }' | jq .
```

**Large batch with custom policy:**
```bash
curl -X POST http://localhost:5000/api/batch \
  -H "Content-Type: application/json" \
  -d '{
    "validations": [
      {
        "prompt": "Query 1",
        "output": "Output 1",
        "context": "Context 1",
        "policy": "rag_strict"
      },
      {
        "prompt": "Query 2",
        "output": "Output 2",
        "context": "Context 2",
        "policy": "chatbot"
      }
    ],
    "max_parallel": 2
  }' | jq '.results[] | {decision, risk_score, latency_ms}'
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | Environment: `development`, `production`, `testing` |
| `PORT` | `5000` | Server port |
| `HOST` | `0.0.0.0` | Server host (bind address) |
| `WORKERS` | `1` | Number of worker threads (production) |
| `HG_DEFAULT_POLICY` | `default` | Default validation policy |
| `HG_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HG_PRELOAD_MODELS` | `true` | Preload ML models at startup |
| `HG_WARMUP_TIMEOUT` | `60` | Model preload timeout in seconds |
| `HG_ENABLE_TRACE_EXPORT` | `false` | Export traces to Langfuse |
| `HG_TRACE_DIR` | `~/.verdict/traces` | Trace output directory |
| `HG_ENABLE_ARMORIQ` | `false` | Enable ArmorIQ intent enforcement |

### Example Configuration

```bash
# Development with debug logging
FLASK_ENV=development HG_LOG_LEVEL=DEBUG python server/run.py

# Production with trace export
FLASK_ENV=production \
  HG_DEFAULT_POLICY=rag_strict \
  HG_ENABLE_TRACE_EXPORT=true \
  WORKERS=4 \
  python server/run.py

# Testing with fast model preload (skip models)
FLASK_ENV=testing HG_PRELOAD_MODELS=false python server/run.py
```

## Available Policies

The following validation policies are available:

| Policy | Description | Best For | Latency |
|--------|-------------|----------|---------|
| `default` | Balanced general-purpose | Most use cases | ~50ms p95 |
| `rag_strict` | High-risk domains | Healthcare, finance, legal | ~80ms p95 |
| `chatbot` | Low-latency, relaxed | Conversational AI | ~30ms p95 |

Use any policy in requests: `"policy": "rag_strict"`

## Error Handling

All errors follow a standard format:

```json
{
  "error": "Human-readable error message",
  "code": "ERROR_CODE",
  "details": {
    "field": "optional context"
  }
}
```

### HTTP Status Codes

| Code | Reason | Example |
|------|--------|---------|
| `200` | Success | Validation completed |
| `400` | Bad Request | Missing required field |
| `403` | Forbidden | ArmorIQ blocked action |
| `404` | Not Found | Invalid endpoint |
| `422` | Validation Error | Invalid request schema |
| `500` | Server Error | Guard initialization failed |
| `503` | Unavailable | Models not loaded |

## Examples

### Python Client Example

```python
import requests
import json

# Single validation
response = requests.post(
    "http://localhost:5000/api/validate",
    json={
        "prompt": "What is AI?",
        "output": "AI is artificial intelligence.",
        "context": "AI stands for artificial intelligence...",
        "policy": "default"
    }
)

decision = response.json()
print(f"Decision: {decision['decision']}")
print(f"Risk: {decision['risk_score']:.2f}")
print(f"Latency: {decision['latency_ms']:.1f}ms")

# Batch validation
batch_response = requests.post(
    "http://localhost:5000/api/batch",
    json={
        "validations": [
            {"prompt": "Q1", "output": "A1", "context": "C1"},
            {"prompt": "Q2", "output": "A2", "context": "C2"},
        ],
        "max_parallel": 1
    }
)

batch = batch_response.json()
print(f"Processed: {batch['processed_count']}")
print(f"Total time: {batch['total_time_ms']:.1f}ms")
```

### JavaScript/Node.js Client Example

```javascript
// Single validation
const response = await fetch('http://localhost:5000/api/validate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    prompt: 'What is AI?',
    output: 'AI is artificial intelligence.',
    context: 'AI stands for artificial intelligence...',
    policy: 'default'
  })
});

const decision = await response.json();
console.log(`Decision: ${decision.decision}`);
console.log(`Risk: ${decision.risk_score.toFixed(2)}`);
console.log(`Latency: ${decision.latency_ms.toFixed(1)}ms`);
```

## Monitoring & Logging

### Request Logging

All requests are logged with unique IDs and latency:

```
INFO - server.routes - [a1b2c3d4] POST /api/validate | client=127.0.0.1
DEBUG - server.routes - Validating: prompt=What is AI?..., output=AI is..., context_len=125
INFO - server.routes - Validation result: decision=allow, risk=0.150, latency=48.5ms
INFO - server.routes - [a1b2c3d4] POST /api/validate | status=200 | latency=49.2ms
```

### Performance Metrics

Enable latency tracking to monitor performance:

```bash
# Set log level to DEBUG to see detailed timing
HG_LOG_LEVEL=DEBUG python server/run.py
```

Typical latencies (measured on M1 Mac):
- **Heuristics Tier**: 2-5ms
- **Embedding Tier**: 15-30ms
- **HHEM Tier**: 40-80ms
- **Total (p95)**: 50-100ms

## Testing

Run the API server in one terminal and test with curl in another:

```bash
# Terminal 1: Start server
python server/run.py

# Terminal 2: Test health
curl http://localhost:5000/api/health | jq .

# Test validation
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Test",
    "output": "Test output",
    "context": "Test context"
  }' | jq .

# Test batch
curl -X POST http://localhost:5000/api/batch \
  -H "Content-Type: application/json" \
  -d '{
    "validations": [
      {"prompt": "Q", "output": "A", "context": "C"}
    ]
  }' | jq .
```

## Integration with Node.js SDK

This API is designed to be called by the `guardly-node-sdk`:

```typescript
import { Guard } from 'guardly-node-sdk';

const guard = new Guard({
  apiEndpoint: 'http://localhost:5000/api',
  policy: 'default'
});

const decision = await guard.validate({
  prompt: 'What is AI?',
  output: 'AI is artificial intelligence.',
  context: 'AI stands for artificial intelligence...'
});

console.log(decision.decision); // 'allow'
```

## Production Deployment

### Docker

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY . .

RUN pip install -e ".[dev]"

EXPOSE 5000
CMD ["python", "server/run.py"]
```

Run with:
```bash
docker build -t verdict-api .
docker run -p 5000:5000 -e FLASK_ENV=production verdict-api
```

### Gunicorn (Production WSGI)

```bash
pip install gunicorn

# Run with 4 workers
gunicorn -w 4 -b 0.0.0.0:5000 'server:create_app()'
```

### Load Testing

```bash
# Using locust for load testing
pip install locust

# Create locustfile.py (see examples/)
locust -f locustfile.py --host=http://localhost:5000
```

## Troubleshooting

### Models not loading
```
[Warmup] Model preload failed: CUDA out of memory
```

**Solution:** Set `HG_PRELOAD_MODELS=false` to disable background preload, or increase system memory.

### Slow first request
First request may take 6-8 seconds while models load. Enable preload:
```bash
HG_PRELOAD_MODELS=true python server/run.py
```

### CORS errors
Ensure CORS middleware is enabled (it is by default). If calling from browser:
```
Access-Control-Allow-Origin: *
```

### Policy not found
Ensure policy file exists in `policies/` directory:
```bash
ls -la policies/*.yaml
```

Available policies: `default`, `rag_strict`, `chatbot`, `safe`, `development`

## Contributing

To extend the API:

1. Add new schemas in `server/schemas.py`
2. Add new routes in `server/routes.py`
3. Register routes in `create_routes()`
4. Test with curl or Python requests

## License

MIT - See LICENSE file
