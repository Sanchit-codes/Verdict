# HallucinationGuard API Reference

Complete specification of the HallucinationGuard Flask REST API endpoints, request/response schemas, error codes, and examples.

## Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/validate` | `POST` | Validate single LLM output for hallucinations |
| `/api/batch_validate` | `POST` | Validate multiple outputs in parallel or sequential mode |
| `/api/health` | `GET` | Health check and model availability status |
| `/api/version` | `GET` | API and SDK version information |

## Base URL

```
http://localhost:5000/api
```

---

## Endpoints

### 1. POST /api/validate

Validate a single LLM output for hallucinations using the 3-tier cascade.

#### Request

**Headers:**

```http
Content-Type: application/json
```

**Body:**

```json
{
  "prompt": "What is the capital of France?",
  "output": "The capital of France is Paris.",
  "context": "France is a country in Western Europe. Its capital is Paris.",
  "policy": "default",
  "domain": "geography",
  "use_refinement": false
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | ✓ | Original user prompt or query |
| `output` | string | ✓ | Generated LLM output to validate |
| `context` | string | ✗ | Reference context for fact-checking |
| `policy` | string | ✗ | Policy name (default: "default") |
| `domain` | string | ✗ | Domain context (e.g., "medical", "finance") |
| `use_refinement` | boolean | ✗ | Enable refinement suggestions (default: false) |

#### Response

**Status Code: 200 OK**

```json
{
  "decision": "allow",
  "risk_score": 0.15,
  "confidence": 0.92,
  "evidence": "Output matches context with high cosine similarity (0.95).",
  "output": "The capital of France is Paris.",
  "latency_ms": 48.5,
  "policy_name": "default",
  "tier_results": [
    {
      "validator_name": "heuristics",
      "score": 0.85,
      "passed": true,
      "evidence": "Entity overlap: 1.0, context coverage: 0.9",
      "latency_ms": 2.1
    },
    {
      "validator_name": "embedding",
      "score": 0.95,
      "passed": true,
      "evidence": "Cosine similarity: 0.95",
      "latency_ms": 15.3
    },
    {
      "validator_name": "hhem",
      "score": 0.76,
      "passed": true,
      "evidence": "Faithfulness: 0.76",
      "latency_ms": 22.1
    }
  ],
  "preprocessing_metadata": {
    "core_task": "geography_question",
    "entities": ["France", "Paris"],
    "context_requirements": ["location", "capital"],
    "fast_mode_applied": false
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `decision` | string | One of: `allow`, `block`, `regenerate`, `abstain` |
| `risk_score` | number | Risk score 0.0-1.0 (0=safe, 1=dangerous) |
| `confidence` | number | Confidence in decision 0.0-1.0 |
| `evidence` | string | Human-readable explanation |
| `output` | string | The validated output (same as input) |
| `latency_ms` | number | Total validation latency in milliseconds |
| `policy_name` | string | Name of policy used |
| `tier_results` | array | Per-validator results (Tier 1, 2, 3) |
| `preprocessing_metadata` | object | Analysis metadata from preprocessing |
| `suggested_fix` | string | *(optional)* If decision="regenerate" |

#### Error Responses

**Status Code: 400 Bad Request**

```json
{
  "error": "ValidationError",
  "message": "prompt is required",
  "details": {
    "field": "prompt",
    "reason": "Missing required field"
  }
}
```

**Status Code: 422 Unprocessable Entity**

```json
{
  "error": "ValidationError",
  "message": "policy 'invalid_policy' not found",
  "details": {
    "field": "policy",
    "reason": "Policy does not exist"
  }
}
```

**Status Code: 504 Gateway Timeout**

```json
{
  "error": "ValidationTimeout",
  "message": "Validation exceeded timeout (30000ms)",
  "details": {
    "latency_ms": 30000,
    "tier": "hhem"
  }
}
```

#### Examples

**curl:**

```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is Python?",
    "output": "Python is a programming language.",
    "context": "Python is a high-level, interpreted programming language.",
    "policy": "default"
  }'
```

**TypeScript:**

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000'
});

const decision = await client.validate({
  prompt: 'What is Python?',
  output: 'Python is a programming language.',
  context: 'Python is a high-level, interpreted programming language.',
  policy: 'default'
});

console.log(decision.decision);    // "allow"
console.log(decision.risk_score);  // 0.15
```

**Python:**

```python
import requests
import json

response = requests.post(
    'http://localhost:5000/api/validate',
    json={
        'prompt': 'What is Python?',
        'output': 'Python is a programming language.',
        'context': 'Python is a high-level, interpreted programming language.',
        'policy': 'default'
    }
)

decision = response.json()
print(decision['decision'])    # "allow"
print(decision['risk_score'])  # 0.15
```

---

### 2. POST /api/batch_validate

Validate multiple outputs efficiently in parallel or sequential mode.

#### Request

**Body:**

```json
{
  "requests": [
    {
      "prompt": "What is Python?",
      "output": "Python is a programming language.",
      "context": "Python is a high-level interpreted language..."
    },
    {
      "prompt": "What is Node.js?",
      "output": "Node.js is a JavaScript runtime.",
      "context": "Node.js is built on Chrome V8..."
    }
  ],
  "mode": "parallel",
  "timeout_per_request_ms": 30000
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `requests` | array | ✓ | Array of validation requests (1-100 items) |
| `mode` | string | ✗ | `parallel` (default) or `sequential` |
| `timeout_per_request_ms` | number | ✗ | Per-request timeout (1000-120000ms, default: 30000) |

Each request object has the same fields as single validate endpoint.

#### Response

**Status Code: 200 OK**

```json
{
  "batch_id": "batch_1714046832_abc123",
  "total_requests": 2,
  "successful_validations": 2,
  "failed_validations": 0,
  "batch_latency_ms": 125.3,
  "errors": [],
  "results": [
    {
      "id": "req_0",
      "decision": "allow",
      "risk_score": 0.12,
      "confidence": 0.95,
      "evidence": "High context match",
      "latency_ms": 42.1
    },
    {
      "id": "req_1",
      "decision": "block",
      "risk_score": 0.78,
      "confidence": 0.88,
      "evidence": "Output contradicts context",
      "latency_ms": 38.2,
      "error": null
    }
  ]
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `batch_id` | string | Unique batch identifier |
| `total_requests` | number | Total requests in batch |
| `successful_validations` | number | Count of successful validations |
| `failed_validations` | number | Count of failed validations |
| `batch_latency_ms` | number | Total batch processing time |
| `errors` | array | Array of error messages |
| `results` | array | Array of per-request results |

#### Error Responses

**Status Code: 400 Bad Request**

```json
{
  "error": "ValidationError",
  "message": "requests array must have 1-100 items",
  "details": {
    "field": "requests",
    "count": 0
  }
}
```

**Status Code: 413 Payload Too Large**

```json
{
  "error": "PayloadTooLarge",
  "message": "Total request payload exceeds 10MB"
}
```

#### Examples

**curl:**

```bash
curl -X POST http://localhost:5000/api/batch_validate \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {
        "prompt": "What is Python?",
        "output": "Python is a programming language.",
        "context": "Python is a high-level interpreted language..."
      },
      {
        "prompt": "What is Node.js?",
        "output": "Node.js is a JavaScript runtime.",
        "context": "Node.js is built on Chrome V8..."
      }
    ],
    "mode": "parallel",
    "timeout_per_request_ms": 30000
  }'
```

**TypeScript:**

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000'
});

const batch = await client.batchValidate({
  requests: [
    {
      prompt: 'What is Python?',
      output: 'Python is a programming language.',
      context: 'Python is a high-level interpreted language...'
    },
    {
      prompt: 'What is Node.js?',
      output: 'Node.js is a JavaScript runtime.',
      context: 'Node.js is built on Chrome V8...'
    }
  ],
  mode: 'parallel',
  timeout_per_request_ms: 30000
});

console.log(`Total: ${batch.total_requests}`);
console.log(`Allowed: ${batch.results.filter(r => r.decision === 'allow').length}`);
console.log(`Blocked: ${batch.results.filter(r => r.decision === 'block').length}`);
```

**Python:**

```python
import requests

response = requests.post(
    'http://localhost:5000/api/batch_validate',
    json={
        'requests': [
            {
                'prompt': 'What is Python?',
                'output': 'Python is a programming language.',
                'context': 'Python is a high-level interpreted language...'
            },
            {
                'prompt': 'What is Node.js?',
                'output': 'Node.js is a JavaScript runtime.',
                'context': 'Node.js is built on Chrome V8...'
            }
        ],
        'mode': 'parallel',
        'timeout_per_request_ms': 30000
    }
)

batch = response.json()
print(f"Total: {batch['total_requests']}")
print(f"Successful: {batch['successful_validations']}")
print(f"Failed: {batch['failed_validations']}")
```

---

### 3. GET /api/health

Health check endpoint returning server and model status.

#### Request

```http
GET /api/health HTTP/1.1
Host: localhost:5000
```

No request body required.

#### Response

**Status Code: 200 OK**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-04-05T12:30:45.123Z",
  "uptime_seconds": 3600,
  "models_ready": {
    "heuristics": true,
    "embedding": true,
    "hhem": true
  },
  "policy_loaded": "default",
  "memory_mb": 2048,
  "request_latency_p95_ms": 48.5
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `healthy`, `degraded`, or `unhealthy` |
| `version` | string | API server version |
| `timestamp` | string | Current server time (ISO 8601) |
| `uptime_seconds` | number | Seconds since server started |
| `models_ready` | object | Per-validator model availability |
| `policy_loaded` | string | Currently loaded default policy |
| `memory_mb` | number | Memory usage in MB |
| `request_latency_p95_ms` | number | p95 latency of recent requests |

#### Response Status Codes

| Status | Condition |
|--------|-----------|
| 200 OK | All systems operational |
| 503 Service Unavailable | Server not ready (models loading) |
| 503 Service Unavailable | Critical models failed to load |

#### Examples

**curl:**

```bash
curl http://localhost:5000/api/health
```

**TypeScript:**

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000'
});

const health = await client.getHealth();
console.log('Status:', health.status);  // "healthy"
console.log('Version:', health.version);  // "1.0.0"
```

**Python:**

```python
import requests

response = requests.get('http://localhost:5000/api/health')
health = response.json()

print(f"Status: {health['status']}")
print(f"Version: {health['version']}")
print(f"Models: {health['models_ready']}")
```

---

### 4. GET /api/version

Version information for API and SDK components.

#### Request

```http
GET /api/version HTTP/1.1
Host: localhost:5000
```

#### Response

**Status Code: 200 OK**

```json
{
  "api_version": "1.0.0",
  "sdk_version": "1.0.0",
  "python_version": "3.10.8",
  "flask_version": "2.3.2",
  "hallucination_guard_version": "1.0.0",
  "models": {
    "heuristics": "1.0",
    "embedding": "all-MiniLM-L6-v2",
    "hhem": "vectara/hallucination_evaluation_model"
  },
  "build_timestamp": "2024-04-05T12:00:00Z"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `api_version` | string | Flask API server version |
| `sdk_version` | string | HallucinationGuard SDK version |
| `python_version` | string | Python interpreter version |
| `flask_version` | string | Flask framework version |
| `hallucination_guard_version` | string | Core SDK version |
| `models` | object | Per-tier model names/versions |
| `build_timestamp` | string | Build timestamp (ISO 8601) |

#### Examples

**curl:**

```bash
curl http://localhost:5000/api/version
```

**TypeScript:**

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000'
});

const version = await client.getVersion();
console.log('API Version:', version.api_version);
console.log('SDK Version:', version.sdk_version);
console.log('Models:', version.models);
```

---

## Error Codes

### Client Errors (4xx)

| Code | Error | Cause | Solution |
|------|-------|-------|----------|
| 400 | `BadRequest` | Invalid request format | Check JSON syntax and required fields |
| 400 | `ValidationError` | Missing required field | Provide all required parameters |
| 422 | `ValidationError` | Invalid field value | Check parameter ranges and types |
| 422 | `PolicyNotFound` | Policy doesn't exist | Use valid policy name: default, rag_strict, chatbot |
| 429 | `RateLimited` | Too many requests | Slow down request rate, implement backoff |

### Server Errors (5xx)

| Code | Error | Cause | Solution |
|------|-------|-------|----------|
| 500 | `InternalServerError` | Unexpected server error | Check server logs |
| 503 | `ServiceUnavailable` | Models not loaded | Wait for models to preload or disable slow models |
| 504 | `ValidationTimeout` | Validation exceeded timeout | Increase timeout_ms or disable Tier 3 |

### Error Response Format

All errors follow this format:

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "details": {
    "field": "prompt",
    "reason": "Missing required field",
    "timestamp": "2024-04-05T12:30:45.123Z"
  }
}
```

---

## Decision Types

The `decision` field can be one of:

| Decision | Meaning | Action |
|----------|---------|--------|
| `allow` | Output is safe and faithful | Return to user |
| `block` | Output likely contains hallucinations | Reject output, return error to user |
| `regenerate` | Output might be improved | Retry generation with hint |
| `abstain` | Cannot determine due to error/timeout | Return output as-is or retry |

---

## Policy Reference

### Built-in Policies

#### default

General-purpose policy for balanced performance and accuracy.

```json
{
  "name": "default",
  "latency_budget_ms": 200,
  "risk_threshold": 0.5,
  "validators": {
    "heuristics": { "weight": 0.2, "threshold": 0.5 },
    "embedding": { "weight": 0.3, "threshold": 0.7 },
    "hhem": { "weight": 0.5, "threshold": 0.8 }
  }
}
```

#### rag_strict

Strict policy for high-risk domains (healthcare, finance, legal).

```json
{
  "name": "rag_strict",
  "latency_budget_ms": 300,
  "risk_threshold": 0.3,
  "validators": {
    "heuristics": { "weight": 0.2, "threshold": 0.6 },
    "embedding": { "weight": 0.3, "threshold": 0.75 },
    "hhem": { "weight": 0.5, "threshold": 0.85 }
  }
}
```

#### chatbot

Low-latency policy for chatbots (skips Tier 3).

```json
{
  "name": "chatbot",
  "latency_budget_ms": 100,
  "risk_threshold": 0.6,
  "validators": {
    "heuristics": { "weight": 0.4, "threshold": 0.5 },
    "embedding": { "weight": 0.6, "threshold": 0.65 }
  }
}
```

---

## Rate Limiting

Currently, the API has no strict rate limits, but production deployments should implement:

- **Per-IP limit**: 100 requests/minute
- **Per-API key limit**: 1000 requests/minute
- **Batch size**: 1-100 requests per batch_validate call

Exceeding limits returns `429 Too Many Requests`.

---

## Caching & Performance

- **Model caching**: All models are cached after first load (no re-downloads)
- **Policy caching**: Policies are cached after first load
- **Request caching**: No request caching (each validation is fresh)

---

## Timeout Specifications

| Component | Timeout | Notes |
|-----------|---------|-------|
| Tier 1 (Heuristics) | 5 ms | Usually completes in <2ms |
| Tier 2 (Embedding) | 30 ms | Usually completes in <20ms |
| Tier 3 (HHEM) | 80 ms | Usually completes in <50ms |
| Total Validation | 200 ms | Sum may exceed due to parallelization |
| Request Timeout | 30000 ms | Client-side HTTP timeout |

---

## Examples by Use Case

### RAG System with Healthcare Content

```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Is this medication safe during pregnancy?",
    "output": "This medication is generally considered safe.",
    "context": "FDA warning: Avoid this medication during pregnancy.",
    "policy": "rag_strict",
    "domain": "medical"
  }'
```

### Chatbot with Low-Latency Requirement

```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Tell me a joke",
    "output": "Why did the chicken cross the road? To get to the other side!",
    "policy": "chatbot"
  }'
```

### Batch Processing 50 Documents

```bash
curl -X POST http://localhost:5000/api/batch_validate \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"prompt": "Q1?", "output": "A1", "context": "C1"},
      ...50 requests...
    ],
    "mode": "parallel",
    "timeout_per_request_ms": 60000
  }'
```

---

For integration examples and detailed usage, see [SDK_INTEGRATION_GUIDE.md](./SDK_INTEGRATION_GUIDE.md) and [EXAMPLES.md](./EXAMPLES.md).
