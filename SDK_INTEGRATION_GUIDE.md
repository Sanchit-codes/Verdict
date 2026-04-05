# HallucinationGuard SDK Integration Guide

Complete guide to integrating HallucinationGuard across your application stack. This covers the **3-layer architecture**: Node.js client → Flask server → Python SDK.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Node.js Client Setup](#nodejs-client-setup)
3. [Flask Server Setup](#flask-server-setup)
4. [Configuration & Policy Selection](#configuration--policy-selection)
5. [Request/Response Flow](#requestresponse-flow)
6. [Error Handling](#error-handling)
7. [Retry Configuration](#retry-configuration)
8. [Batch Validation](#batch-validation)
9. [Deployment](#deployment)

## Architecture Overview

### 3-Layer Stack

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Client Applications                                │
│ (Node.js, React, Vue, Express, Fastify, etc.)              │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/REST
                     │ JSON requests
                     │
┌────────────────────▼────────────────────────────────────────┐
│ Layer 2: Flask REST API Server                              │
│ • Validation endpoint (/api/validate)                       │
│ • Batch validation (/api/batch_validate)                    │
│ • Health check (/api/health)                                │
│ • Version info (/api/version)                               │
└────────────────────┬────────────────────────────────────────┘
                     │ Python SDK
                     │ Guard.validate()
                     │
┌────────────────────▼────────────────────────────────────────┐
│ Layer 3: HallucinationGuard Python Engine                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Validation Pipeline (3-tier cascade)                    │ │
│ │                                                          │ │
│ │ Tier 1: Heuristics            [< 5ms]                 │ │
│ │   • Context coverage ratio                              │ │
│ │   • Entity overlap check                                │ │
│ │   • Length anomaly detection                            │ │
│ │                                                          │ │
│ │ Tier 2: Embedding Similarity  [< 30ms]                │ │
│ │   • all-MiniLM-L6-v2 embeddings                         │ │
│ │   • Cosine similarity scoring                           │ │
│ │                                                          │ │
│ │ Tier 3: HHEM Classifier       [< 80ms]                │ │
│ │   • vectara/hallucination_evaluation_model              │ │
│ │   • Faithfulness scoring                                │ │
│ │                                                          │ │
│ │ Decision Engine                                          │ │
│ │   • Weighted score aggregation                          │ │
│ │   • Policy-driven thresholds                            │ │
│ │   • Risk classification                                 │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                              │
│ Models (auto-downloaded on first use):                      │
│ • HHEM 2.1-Open (400MB) – Tier 3 faithfulness classifier   │
│ • all-MiniLM-L6-v2 (80MB) – Tier 2 embeddings              │
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User Input
    ↓
Client Library (guardly-node-sdk)
    ├─ Validate input (prompt, output, context)
    ├─ Add retry configuration
    └─ Send POST /validate
        ↓
    Flask Server (server/routes.py)
    ├─ Parse request
    ├─ Load policy
    └─ Call Guard.validate()
        ↓
    Python SDK (hallucination_guard/core/guard.py)
    ├─ Tier 1: Heuristics
    ├─ Tier 2: Embedding (if needed)
    ├─ Tier 3: HHEM (if needed)
    ├─ Aggregate scores
    └─ Generate decision
        ↓
    Response (ValidationDecision)
    ├─ decision: "allow" | "block" | "regenerate" | "abstain"
    ├─ risk_score: 0.0-1.0
    ├─ evidence: explanation
    └─ tier_results: per-validator scores
        ↓
Client (decision.decision === 'allow' ? sendToUser : logError)
```

## Node.js Client Setup

### Installation

```bash
npm install guardly-node-sdk
```

### Basic Initialization

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000',  // Flask server URL
  timeout: 30000  // Request timeout in ms
});
```

### Configuration Options

```typescript
interface GuardlyClientConfig {
  // Required
  apiKey: string;

  // Optional - Connection
  baseUrl?: string;  // Default: http://localhost:5000
  timeout?: number;  // Default: 30000 (ms)
  userAgent?: string;  // Custom User-Agent header

  // Optional - Error Handling
  gracefulErrorHandling?: boolean;  // Return abstain on error instead of throwing

  // Optional - Retry Logic
  retryConfig?: {
    maxAttempts: number;  // Default: 3
    initialDelayMs: number;  // Default: 100
    backoffMultiplier: number;  // Default: 2 (exponential)
    maxDelayMs: number;  // Default: 10000
    jitterFactor: number;  // Default: 0.1 (±10%)
  };
}
```

### Example: Full Configuration

```typescript
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY,
  baseUrl: process.env.GUARDLY_URL || 'http://localhost:5000',
  timeout: 60000,  // 60 second timeout
  gracefulErrorHandling: true,  // Don't throw on network errors
  retryConfig: {
    maxAttempts: 5,  // Retry up to 5 times
    initialDelayMs: 200,  // Start with 200ms delay
    backoffMultiplier: 2.5,  // Exponential backoff: 200 → 500 → 1250 → ...
    maxDelayMs: 30000,  // Cap at 30 seconds
    jitterFactor: 0.15  // Add ±15% jitter to avoid thundering herd
  }
});
```

## Flask Server Setup

### Installation

```bash
# Install with all dependencies
pip install -e ".[dev]"

# Or install just Flask
pip install flask>=2.0.0
```

### Starting the Server

```bash
# Quick start (uses defaults)
python server/run.py

# Or use Flask CLI
FLASK_APP=server:create_app flask run

# Custom port
PORT=3000 python server/run.py

# Production mode
FLASK_ENV=production python server/run.py
```

### Environment Variables

```bash
# API Configuration
HG_DEFAULT_POLICY=default  # Policy to load: default, rag_strict, chatbot
HG_API_KEY_REQUIRED=false  # Require API key authentication
HG_CORS_ORIGINS=*          # CORS origins (default: *)

# Model Configuration
HG_PRELOAD_MODELS=true     # Preload models on startup
HG_DISABLE_HHEM=false      # Skip Tier 3 (fast mode)
HG_MODEL_CACHE=/path       # Model cache directory

# Server
FLASK_ENV=development      # Environment: development or production
PORT=5000                  # Server port
DEBUG=false                # Flask debug mode

# Logging
HG_LOG_LEVEL=INFO          # Logging: DEBUG, INFO, WARNING, ERROR
```

### Server Code Structure

```
server/
├── __init__.py           # Flask app factory
├── run.py               # Entry point
├── config.py            # Configuration management
├── routes.py            # API endpoint handlers
├── schemas.py           # Request/response Pydantic models
├── middleware.py        # Request logging, metrics
├── errors.py            # Error handling
└── requirements.txt     # Dependencies
```

## Configuration & Policy Selection

### Built-in Policies

| Policy | Use Case | Tier 1 | Tier 2 | Tier 3 | Threshold |
|--------|----------|--------|--------|--------|-----------|
| `default` | General purpose | ✓ | ✓ | ✓ | 0.5 |
| `rag_strict` | Healthcare, Finance | ✓ | ✓ | ✓ | 0.3 |
| `chatbot` | Low-latency chat | ✓ | ✓ | ✗ | 0.6 |

### Using Policies

**TypeScript Client:**

```typescript
// Use default policy
const decision = await client.validate({
  prompt: 'What is Python?',
  output: 'Python is a programming language.'
  // No policy specified = uses server default
});

// Use specific policy
const decision = await client.validate({
  prompt: 'Is vaccine X safe?',
  output: 'Yes, vaccine X is safe for all populations.',
  context: 'Medical literature: Vaccine X has mild side effects in 5% of patients...',
  policy: 'rag_strict'  // Strict policy for medical Q&A
});

// Use custom domain context
const decision = await client.validate({
  prompt: 'What does this error mean?',
  output: 'This error means memory allocation failed.',
  domain: 'engineering'  // Domain-specific context
});
```

**Python SDK:**

```python
from hallucination_guard import Guard

# Load specific policy
guard = Guard(policy='rag_strict')

# Use for validation
decision = guard.validate(
    prompt='Is this medication safe during pregnancy?',
    output='Yes, it is generally safe.',
    context='FDA warning: Avoid during pregnancy.',
    domain='medical'
)
```

### Creating Custom Policies

```yaml
# policies/my_policy.yaml
name: "my_policy"
description: "Custom policy for RAG systems"
latency_budget_ms: 200
risk_threshold: 0.4

validators:
  - name: "heuristics"
    enabled: true
    weight: 0.2
    threshold: 0.5
    timeout_ms: 5

  - name: "embedding"
    enabled: true
    weight: 0.3
    threshold: 0.7
    timeout_ms: 30

  - name: "hhem"
    enabled: true
    weight: 0.5
    threshold: 0.75
    timeout_ms: 100

mitigation:
  on_block: "block"      # Action if blocked: block, regenerate, abstain
  on_timeout: "abstain"  # Action if timeout: abstain, allow
  on_error: "abstain"    # Action if error: abstain, allow, block
```

Load it:

```typescript
const decision = await client.validate({
  prompt: '...',
  output: '...',
  policy: 'my_policy'
});
```

## Request/Response Flow

### Single Validation

**Request (Client → Server):**

```typescript
const decision = await client.validate({
  prompt: 'What is climate change?',
  output: 'Climate change is the warming of the Earth caused by human activities.',
  context: 'From IPCC: Global warming refers to the long-term heating...',
  policy: 'default',
  domain: 'science',
  use_refinement: true  // Enable suggested fixes
});
```

**HTTP Request (under the hood):**

```http
POST /api/validate HTTP/1.1
Host: localhost:5000
Content-Type: application/json

{
  "prompt": "What is climate change?",
  "output": "Climate change is the warming of the Earth caused by human activities.",
  "context": "From IPCC: Global warming refers to the long-term heating...",
  "policy": "default",
  "domain": "science",
  "use_refinement": true
}
```

**Response (Server → Client):**

```json
{
  "decision": "allow",
  "risk_score": 0.18,
  "confidence": 0.94,
  "evidence": "Output aligns well with provided context (cosine similarity: 0.92)",
  "output": "Climate change is the warming of the Earth caused by human activities.",
  "latency_ms": 42.5,
  "policy_name": "default",
  "tier_results": [
    {
      "validator_name": "heuristics",
      "score": 0.88,
      "passed": true,
      "evidence": "Context coverage ratio: 0.85",
      "latency_ms": 2.1
    },
    {
      "validator_name": "embedding",
      "score": 0.92,
      "passed": true,
      "evidence": "Cosine similarity: 0.92",
      "latency_ms": 18.3
    },
    {
      "validator_name": "hhem",
      "score": 0.76,
      "passed": true,
      "evidence": "Faithfulness score: 0.76",
      "latency_ms": 22.1
    }
  ]
}
```

### Batch Validation

**Request:**

```typescript
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
  mode: 'parallel',  // 'parallel' or 'sequential'
  timeout_per_request_ms: 30000
});
```

**HTTP Request:**

```http
POST /api/batch_validate HTTP/1.1
Host: localhost:5000
Content-Type: application/json

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

**Response:**

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
      "decision": "allow",
      "risk_score": 0.08,
      "confidence": 0.97,
      "evidence": "Perfect context match",
      "latency_ms": 38.2
    }
  ]
}
```

## Error Handling

### Error Classes

```typescript
import {
  GuardlyError,           // Base error class
  GuardlyApiError,        // API errors (4xx, 5xx)
  GuardlyNetworkError,    // Network errors (connection refused, timeout)
  GuardlyValidationError  // Input validation errors
} from 'guardly-node-sdk';
```

### Handling Errors

```typescript
const client = new GuardlyClient({ apiKey: 'key', baseUrl: 'http://localhost:5000' });

try {
  const decision = await client.validate({
    prompt: 'What is X?',
    output: 'X is Y.'
  });
  
  if (decision.decision === 'allow') {
    // Safe to use
  } else {
    // Handle blocked response
  }
} catch (error) {
  if (error instanceof GuardlyValidationError) {
    // Input validation failed (missing required fields, etc.)
    console.error(`Validation error: ${error.message}`);
    console.error(`Field: ${error.field}`);
  } else if (error instanceof GuardlyNetworkError) {
    // Network error (connection refused, timeout, etc.)
    console.error(`Network error: ${error.message}`);
    // Retry logic can be implemented here
  } else if (error instanceof GuardlyApiError) {
    // Server error
    console.error(`API error ${error.statusCode}: ${error.message}`);
    if (error.statusCode === 429) {
      console.log('Rate limited, backing off...');
    }
  } else {
    // Unknown error
    console.error(error);
  }
}
```

### Graceful Error Handling

Instead of throwing errors, return "abstain" decision:

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000',
  gracefulErrorHandling: true  // ← Enable graceful mode
});

// On network error, returns { decision: 'abstain', risk_score: 0.5 }
// instead of throwing GuardlyNetworkError
const decision = await client.validate({
  prompt: 'What is X?',
  output: 'X is Y.'
});

// Always safe to access decision
if (decision.decision === 'allow') {
  console.log('Safe to use');
} else if (decision.decision === 'abstain') {
  console.log('Unable to validate, but returning output as-is');
}
```

## Retry Configuration

### Default Behavior

By default, the client retries network errors with exponential backoff:

```
Attempt 1: Immediate
Attempt 2: 100ms + jitter (±10%)
Attempt 3: 200ms + jitter (exponential: 100 * 2)
Attempt 4: 400ms + jitter
... (max 10000ms between retries)
```

### Custom Retry Configuration

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000',
  retryConfig: {
    maxAttempts: 5,              // Try up to 5 times
    initialDelayMs: 50,          // Start with 50ms
    backoffMultiplier: 3,        // Triple the delay each time
    maxDelayMs: 20000,           // Don't exceed 20s between attempts
    jitterFactor: 0.2            // Add ±20% randomness
  }
});
```

### Disable Retries

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000',
  retryConfig: {
    maxAttempts: 1  // No retries
  }
});
```

## Batch Validation

### Sequential Mode

Process requests one at a time (useful when order matters or to reduce concurrent load):

```typescript
const batch = await client.batchValidate({
  requests: [
    { prompt: 'Q1?', output: 'A1', context: 'C1' },
    { prompt: 'Q2?', output: 'A2', context: 'C2' },
    { prompt: 'Q3?', output: 'A3', context: 'C3' }
  ],
  mode: 'sequential',
  timeout_per_request_ms: 30000
});

// Processes: Q1 → Q2 → Q3 (one at a time)
// Total latency ≈ sum of individual latencies
```

### Parallel Mode (Faster)

Process all requests concurrently:

```typescript
const batch = await client.batchValidate({
  requests: [
    { prompt: 'Q1?', output: 'A1', context: 'C1' },
    { prompt: 'Q2?', output: 'A2', context: 'C2' },
    { prompt: 'Q3?', output: 'A3', context: 'C3' }
  ],
  mode: 'parallel',
  timeout_per_request_ms: 30000
});

// Processes all at once
// Total latency ≈ max(individual latencies)
```

### Batch Processing with Error Recovery

```typescript
const batch = await client.batchValidate({
  requests: largeBatchOfRequests,
  mode: 'parallel',
  timeout_per_request_ms: 30000
});

const allowed = batch.results.filter(r => r.decision === 'allow');
const blocked = batch.results.filter(r => r.decision === 'block');
const failed = batch.results.filter(r => r.error);

console.log(`✓ Allowed: ${allowed.length}`);
console.log(`✗ Blocked: ${blocked.length}`);
console.log(`⚠ Failed: ${failed.length}`);

if (failed.length > 0) {
  console.log('Errors:', batch.errors);
  // Retry failed items
  const retryRequests = largeB atchOfRequests.filter(
    (req, idx) => batch.results[idx].error
  );
  const retryBatch = await client.batchValidate({
    requests: retryRequests,
    mode: 'sequential',  // Retry sequentially
    timeout_per_request_ms: 60000  // Longer timeout for retry
  });
}
```

## Deployment

### Production Checklist

- [ ] Set `FLASK_ENV=production`
- [ ] Disable debug mode: `DEBUG=false`
- [ ] Configure API key authentication: `HG_API_KEY_REQUIRED=true`
- [ ] Set CORS origins: `HG_CORS_ORIGINS=https://yourdomain.com`
- [ ] Enable request logging and monitoring
- [ ] Configure timeouts appropriate for your workload
- [ ] Set up health checks: `GET /api/health` every 30 seconds
- [ ] Use a production WSGI server (gunicorn, waitress, etc.)

### Running with Gunicorn (Recommended)

```bash
# Install gunicorn
pip install gunicorn

# Run with 4 worker processes
gunicorn -w 4 -b 0.0.0.0:5000 server:create_app

# With increased timeout (for slow models)
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 server:create_app

# With logging
gunicorn -w 4 -b 0.0.0.0:5000 --access-logfile - --error-logfile - server:create_app
```

### Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY . /app/

RUN pip install -e ".[prod]"
RUN pip install gunicorn

ENV FLASK_ENV=production
ENV PORT=5000
ENV HG_PRELOAD_MODELS=true

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "server:create_app"]
```

Build and run:

```bash
docker build -t hallucination-guard .
docker run -p 5000:5000 -e HG_DEFAULT_POLICY=rag_strict hallucination-guard
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hallucination-guard
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hallucination-guard
  template:
    metadata:
      labels:
        app: hallucination-guard
    spec:
      containers:
      - name: guard
        image: hallucination-guard:latest
        ports:
        - containerPort: 5000
        env:
        - name: HG_DEFAULT_POLICY
          value: "default"
        - name: HG_PRELOAD_MODELS
          value: "true"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /api/health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 5
```

Deploy:

```bash
kubectl apply -f deployment.yaml
```

### Performance Tuning

| Setting | Impact | Notes |
|---------|--------|-------|
| `HG_PRELOAD_MODELS=true` | Cold-start latency ↓ | Takes 30-60s on startup |
| `HG_DISABLE_HHEM=true` | Latency ↓, accuracy ↓ | Fast mode: heuristics + embeddings only |
| Gunicorn workers | Throughput ↑ | 2-4x CPU count recommended |
| Model cache location | Latency ↓ | Use SSD if possible |
| Timeout per request | Error rate changes | Tune based on workload |

---

For quick start and examples, see [QUICKSTART.md](./QUICKSTART.md) and [EXAMPLES.md](./EXAMPLES.md).
