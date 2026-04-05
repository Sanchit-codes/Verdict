# HallucinationGuard Quick Start Guide

Get up and running with HallucinationGuard in 5 minutes. This guide covers the **Node.js client** + **Flask server** + **Python SDK** stack.

## Prerequisites

- **Node.js**: v18 or higher
- **Python**: 3.10 or higher
- **npm** or **yarn** package manager

## Step 1: Install Node SDK (1 minute)

Install the `guardly-node-sdk` package from npm:

```bash
npm install guardly-node-sdk
# or
yarn add guardly-node-sdk
# or
pnpm add guardly-node-sdk
```

## Step 2: Start Flask Server (2 minutes)

The Flask server wraps the Python HallucinationGuard SDK and provides a REST API.

### Option A: Quick Start (Recommended)

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Start the server on http://localhost:5000
python server/run.py
```

You should see:
```
🚀 Starting HallucinationGuard API Server
   Version: 1.0.0
   Environment: DEVELOPMENT
   Policy: default
   Models preload: True
   Listening on 0.0.0.0:5000

   API Docs: http://localhost:5000/api/docs
   Health: http://localhost:5000/api/health
```

### Option B: Custom Configuration

```bash
# Custom port
PORT=3000 python server/run.py

# Strict policy (for healthcare/finance)
HG_DEFAULT_POLICY=rag_strict python server/run.py

# Production mode
FLASK_ENV=production python server/run.py
```

## Step 3: First Validation (2 minutes)

### JavaScript/TypeScript

Create a file `test-validation.ts`:

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

async function main() {
  // Initialize client
  const client = new GuardlyClient({
    apiKey: 'default-key',  // For local dev, any key works
    baseUrl: 'http://localhost:5000'
  });

  // Validate an LLM output
  const decision = await client.validate({
    prompt: 'What is the capital of France?',
    output: 'The capital of France is Paris.',
    context: 'France is a country in Western Europe. Its capital is Paris.',
    domain: 'geography'
  });

  console.log('Decision:', decision.decision);  // Output: "allow"
  console.log('Risk Score:', decision.risk_score);  // 0.15 (low risk)
  console.log('Evidence:', decision.evidence);  // Explanation of the decision
}

main().catch(console.error);
```

Run it:

```bash
npx ts-node test-validation.ts
```

### Node.js (CommonJS)

```javascript
const { GuardlyClient } = require('guardly-node-sdk');

async function main() {
  const client = new GuardlyClient({
    apiKey: 'default-key',
    baseUrl: 'http://localhost:5000'
  });

  const decision = await client.validate({
    prompt: 'What is the capital of France?',
    output: 'The capital of France is Paris.',
    context: 'France is a country in Western Europe. Its capital is Paris.'
  });

  console.log('Decision:', decision.decision);
  console.log('Risk Score:', decision.risk_score);
}

main().catch(console.error);
```

### Python (Direct SDK)

```python
from hallucination_guard import Guard

# Initialize guard
guard = Guard(policy="default")

# Validate output
decision = guard.validate(
    prompt="What is the capital of France?",
    output="The capital of France is Paris.",
    context="France is a country in Western Europe. Its capital is Paris.",
    domain="geography"
)

print(f"Decision: {decision.decision}")  # Output: "allow"
print(f"Risk Score: {decision.risk_score}")  # 0.15
print(f"Evidence: {decision.evidence}")
```

## Common Patterns

### Basic Validation with Context

The most common pattern—validate output against reference context:

**TypeScript:**

```typescript
const client = new GuardlyClient({ apiKey: 'key', baseUrl: 'http://localhost:5000' });

const decision = await client.validate({
  prompt: 'Summarize this paper.',
  output: 'The paper discusses climate change and its effects on sea levels.',
  context: 'Paper excerpt: Climate change is causing global warming, which is melting ice sheets and raising sea levels...'
});

if (decision.decision === 'allow') {
  console.log('✓ Output is accurate, safe to return to user');
} else if (decision.decision === 'block') {
  console.log('✗ Output contains hallucinations, blocked');
} else if (decision.decision === 'regenerate') {
  console.log('↻ Output may need refinement, suggested fix:', decision.suggested_fix);
}
```

### Batch Validation (Multiple Documents)

Validate multiple outputs in parallel:

**TypeScript:**

```typescript
const client = new GuardlyClient({ apiKey: 'key', baseUrl: 'http://localhost:5000' });

const batch = await client.batchValidate({
  requests: [
    {
      prompt: 'What is Python?',
      output: 'Python is a programming language.',
      context: 'Python is a high-level, interpreted programming language.'
    },
    {
      prompt: 'What is Node.js?',
      output: 'Node.js is a JavaScript runtime.',
      context: 'Node.js is a JavaScript runtime built on Chrome\'s V8 engine.'
    }
  ],
  mode: 'parallel',  // Process in parallel (faster)
  timeout_per_request_ms: 30000
});

console.log(`Total: ${batch.total_requests}`);
console.log(`Successful: ${batch.successful_validations}`);
console.log(`Failed: ${batch.failed_validations}`);

batch.results.forEach((result, index) => {
  console.log(`[${index}] Decision: ${result.decision}, Risk: ${result.risk_score}`);
});
```

### With Custom Policy

Use domain-specific policies for stricter validation:

**TypeScript:**

```typescript
const client = new GuardlyClient({ apiKey: 'key', baseUrl: 'http://localhost:5000' });

// For medical/financial content, use strict policy
const decision = await client.validate({
  prompt: 'Is this medication safe for pregnant women?',
  output: 'Yes, this medication is generally safe during pregnancy.',
  context: 'FDA warning: This medication should be avoided during pregnancy due to teratogenic effects.',
  policy: 'rag_strict'  // Stricter threshold, lower risk tolerance
});

if (decision.decision !== 'allow') {
  console.log('Blocked due to safety concern');
}
```

## Checking API Health

Verify the server is running:

**curl:**

```bash
curl http://localhost:5000/api/health
```

**TypeScript:**

```typescript
const client = new GuardlyClient({ apiKey: 'key', baseUrl: 'http://localhost:5000' });
const health = await client.getHealth();
console.log('Status:', health.status);  // "healthy"
console.log('Models:', health.models_ready);
```

## Error Handling

Handle errors gracefully:

**TypeScript:**

```typescript
import { GuardlyApiError, GuardlyNetworkError, GuardlyValidationError } from 'guardly-node-sdk';

const client = new GuardlyClient({ apiKey: 'key', baseUrl: 'http://localhost:5000' });

try {
  const decision = await client.validate({
    prompt: 'What is X?',
    output: 'X is Y.'
  });
} catch (error) {
  if (error instanceof GuardlyValidationError) {
    console.error('Invalid input:', error.message);
  } else if (error instanceof GuardlyNetworkError) {
    console.error('Network error:', error.message);
  } else if (error instanceof GuardlyApiError) {
    console.error('API error:', error.statusCode, error.message);
  }
}
```

## Next Steps

- **API Reference**: See [API_REFERENCE.md](./API_REFERENCE.md) for all endpoint specs
- **Integration Guide**: See [SDK_INTEGRATION_GUIDE.md](./SDK_INTEGRATION_GUIDE.md) for advanced setup
- **Examples**: See [EXAMPLES.md](./EXAMPLES.md) for real-world scenarios
- **Node SDK Docs**: See [guardly-node-sdk/USAGE.md](./guardly-node-sdk/USAGE.md) for detailed SDK reference

## Troubleshooting

### Server fails to start

```bash
# Check Python installation
python --version  # Should be 3.10+

# Check if port 5000 is in use
lsof -i :5000

# Try a different port
PORT=3000 python server/run.py
```

### Client can't connect to server

```bash
# Verify server is running
curl http://localhost:5000/api/health

# Check baseUrl in client configuration
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000'  // Include http://
});

# If running on different machine
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://<server-ip>:5000'
});
```

### Models not loading

```bash
# Disable model preload temporarily
HG_DISABLE_HHEM=true python server/run.py

# Then check logs for specific errors
python server/run.py 2>&1 | grep -i error
```

## Architecture at a Glance

```
┌─────────────────┐
│ Node.js Client  │  guardly-node-sdk
└────────┬────────┘
         │ HTTP
         │ (POST /validate)
         │
┌────────▼──────────────┐
│ Flask REST API        │  server/routes.py
│ (Validation, Batch)   │
└────────┬──────────────┘
         │ Python
         │ (Guard.validate)
         │
┌────────▼──────────────────────┐
│ HallucinationGuard Python SDK  │
│ ┌──────────────────────────┐   │
│ │ Tier 1: Heuristics       │   │  < 5ms
│ ├──────────────────────────┤   │
│ │ Tier 2: Embeddings       │   │  < 30ms
│ ├──────────────────────────┤   │
│ │ Tier 3: HHEM Classifier  │   │  < 80ms
│ └──────────────────────────┘   │
└───────────────────────────────┘
```

## Summary

You now have:
- ✅ Node.js SDK installed
- ✅ Flask server running
- ✅ First validation working
- ✅ Understanding of common patterns

For production deployment, see [SDK_INTEGRATION_GUIDE.md](./SDK_INTEGRATION_GUIDE.md#deployment).
