# HallucinationGuard REST API Documentation

## Overview

The HallucinationGuard REST API provides production-ready endpoints for detecting AI hallucinations in generated text. All endpoints validate requests before processing and return consistent error responses.

**Base URL:** `http://localhost:5000` (default)  
**API Version:** `1.0.0`  
**Authentication:** Bearer token via `Authorization` header

---

## Table of Contents

1. [Authentication](#authentication)
2. [Endpoints](#endpoints)
3. [Error Codes](#error-codes)
4. [Examples](#examples)

---

## Authentication

All validation endpoints (`/validate`, `/validate/batch`) require API key authentication. Public endpoints (`/health`, `/version`, `/config/policies`) do not.

### Bearer Token

Pass your API key as a Bearer token in the `Authorization` header:

```bash
curl -X POST http://localhost:5000/validate \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

**API Keys are configured via environment variable:**

```bash
export GUARDLY_API_KEYS="key1,key2,key3"
```

Multiple keys can be provided separated by commas.

---

## Endpoints

### 1. POST `/validate` — Single Validation

Validate a single LLM output for hallucinations.

#### Request

```json
{
  "prompt": "string (required) — User query or instruction",
  "output": "string (required) — LLM-generated response to validate",
  "context": "string (optional) — Reference context for fact-checking",
  "policy": "string (optional, default: 'default') — Policy name",
  "domain": "string (optional, default: 'general') — Domain/category",
  "use_refinement": "boolean (optional, default: false) — Return preprocessing metadata"
}
```

#### Response (200 OK)

```json
{
  "decision": "allow | block | regenerate | abstain",
  "risk_score": 0.75,
  "confidence": 0.85,
  "evidence": "High overlap detected with context; content appears factually grounded",
  "output": "The capital of France is Paris.",
  "suggested_fix": null,
  "latency_ms": 45,
  "policy_name": "default"
}
```

#### Error Responses

- **400 Bad Request** — Missing required fields (`prompt` or `output`)
- **422 Unprocessable Entity** — Invalid field types or values
- **401 Unauthorized** — Missing or invalid API key
- **503 Service Unavailable** — Validator failure (graceful degradation)

---

### 2. POST `/validate/batch` — Batch Validation

Validate multiple outputs in parallel or sequential mode.

#### Request

```json
{
  "requests": [
    {
      "id": "req_001 (optional) — Request identifier for tracking",
      "prompt": "string (required)",
      "output": "string (required)",
      "context": "string (optional)",
      "policy": "string (optional)",
      "domain": "string (optional)"
    }
  ],
  "mode": "parallel | sequential (optional, default: 'parallel')"
}
```

**Constraints:**
- Max 100 requests per batch
- Individual timeout: 30 seconds
- Batch timeout: 5 minutes overall

#### Response (200 OK)

```json
{
  "batch_id": "batch_123abc...",
  "total_requests": 2,
  "successful_validations": 2,
  "failed_validations": 0,
  "results": [
    {
      "id": "req_001",
      "decision": "allow",
      "risk_score": 0.2,
      "confidence": 0.95,
      "evidence": "High context overlap; factually grounded",
      "latency_ms": 45,
      "error": null
    }
  ],
  "batch_latency_ms": 2150
}
```

---

### 3. GET `/health` — Health Check

Confirm API and validators are operational.

#### Response (200 OK)

```json
{
  "status": "healthy | degraded | unhealthy",
  "timestamp": "2025-01-10T12:00:00Z",
  "validators": {
    "heuristics": { "available": true, "latency_ms": 2 },
    "embedding": { "available": true, "latency_ms": 28 },
    "hhem": { "available": false, "latency_ms": null }
  },
  "uptime_seconds": 3600,
  "requests_processed": 1250
}
```

---

### 4. GET `/version` — Version Information

Return API and component versions.

#### Response (200 OK)

```json
{
  "api_version": "1.0.0",
  "sdk_version": "0.1.0",
  "python_version": "3.10.11",
  "transformers_version": "4.44",
  "torch_version": "2.3.1"
}
```

---

### 5. GET `/config/policies` — List Available Policies

Discover available policy names and their descriptions.

#### Response (200 OK)

```json
{
  "policies": [
    {
      "name": "default",
      "description": "Balanced general-purpose policy",
      "risk_threshold": 0.5,
      "validators_enabled": ["heuristics", "embedding", "hhem"]
    },
    {
      "name": "rag_strict",
      "description": "High-risk domains (healthcare, finance)",
      "risk_threshold": 0.3,
      "validators_enabled": ["heuristics", "embedding", "hhem"]
    }
  ]
}
```

---

## Error Codes

All errors follow this format:

```json
{
  "status_code": 400,
  "code": "INVALID_INPUT",
  "message": "prompt field is required",
  "timestamp": "2025-01-10T12:00:00Z",
  "request_id": "req_abc123xyz"
}
```

### Status Codes

| Code | Scenario |
|------|----------|
| 200 | Success |
| 400 | Missing/malformed required field |
| 401 | Missing or invalid API key |
| 422 | Field validation failed |
| 429 | Rate limit exceeded |
| 500 | Unhandled server error |
| 503 | Validator failure (graceful degradation) |

---

## Examples

### curl Example

```bash
curl -X POST http://localhost:5000/validate \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "output": "The capital of France is Paris.",
    "context": "France is a country in Western Europe."
  }'
```

### Python Example

```python
import requests

client = requests.Session()
client.headers.update({"Authorization": "Bearer YOUR_API_KEY"})

response = client.post(
    "http://localhost:5000/validate",
    json={
        "prompt": "What is the capital of France?",
        "output": "The capital of France is Paris.",
        "context": "France is a country in Western Europe."
    }
)

print(response.json())
```

### JavaScript Example

```javascript
const GuardlyClient = require('guardly-node-sdk');

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000'
});

const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Western Europe.'
});

console.log(decision);
```

---

## Best Practices

1. **Always provide context** when available for better accuracy
2. **Use batch validation** for multiple validations to improve throughput
3. **Handle 503 responses gracefully** — validators may timeout or become unavailable
4. **Implement exponential backoff** for retries (recommended: 2s, 4s, 8s)
5. **Monitor `/health`** endpoint to detect service degradation
6. **Cache policy list** from `/config/policies` to reduce API calls
7. **Set appropriate timeouts** on your HTTP client (30-60 seconds recommended)

