# Guardly Node.js SDK Usage Guide

Complete reference for the `guardly-node-sdk` TypeScript/JavaScript client library for LLM hallucination detection.

## Table of Contents

1. [Installation](#installation)
2. [Basic Usage](#basic-usage)
3. [Configuration](#configuration)
4. [Single Validation](#single-validation)
5. [Batch Validation](#batch-validation)
6. [Retry Configuration](#retry-configuration)
7. [Error Handling](#error-handling)
8. [Type Reference](#type-reference)
9. [Best Practices](#best-practices)

---

## Installation

### npm

```bash
npm install guardly-node-sdk
```

### yarn

```bash
yarn add guardly-node-sdk
```

### pnpm

```bash
pnpm add guardly-node-sdk
```

## Requires

- **Node.js**: v18 or higher
- **TypeScript**: v5 or higher (optional, but recommended)

---

## Basic Usage

### TypeScript

```typescript
import { GuardlyClient, ValidationDecision } from 'guardly-node-sdk';

// Initialize client
const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000'
});

// Validate a single output
const decision: ValidationDecision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Western Europe. Its capital is Paris.'
});

console.log(decision.decision);  // "allow" | "block" | "regenerate" | "abstain"
console.log(decision.risk_score);  // 0.0-1.0
console.log(decision.confidence);  // 0.0-1.0
```

### JavaScript (CommonJS)

```javascript
const { GuardlyClient } = require('guardly-node-sdk');

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000'
});

async function main() {
  const decision = await client.validate({
    prompt: 'What is the capital of France?',
    output: 'The capital of France is Paris.',
    context: 'France is a country in Western Europe. Its capital is Paris.'
  });

  console.log(decision.decision);
}

main().catch(console.error);
```

### JavaScript (ES Modules)

```javascript
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000'
});

const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Western Europe. Its capital is Paris.'
});

console.log(decision.decision);
```

---

## Configuration

### GuardlyClientConfig

```typescript
interface GuardlyClientConfig {
  // Required: API key for authentication
  apiKey: string;

  // Optional: Base URL of Guardly API
  // Default: 'http://localhost:5000'
  baseUrl?: string;

  // Optional: Request timeout in milliseconds
  // Default: 30000 (30 seconds)
  timeout?: number;

  // Optional: Custom User-Agent header
  // Default: 'guardly-node-sdk/1.0.0 (Node.js <version>)'
  userAgent?: string;

  // Optional: Return "abstain" decision on network error
  // instead of throwing GuardlyNetworkError
  // Default: false
  gracefulErrorHandling?: boolean;

  // Optional: Retry configuration for network failures
  retryConfig?: RetryConfig;
}
```

### Example Configurations

**Local Development:**

```typescript
const client = new GuardlyClient({
  apiKey: 'dev-key',
  baseUrl: 'http://localhost:5000'
});
```

**Production with Retries:**

```typescript
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY,
  baseUrl: process.env.GUARDLY_URL || 'http://localhost:5000',
  timeout: 60000,
  gracefulErrorHandling: true,
  retryConfig: {
    maxAttempts: 5,
    initialDelayMs: 100,
    backoffMultiplier: 2,
    maxDelayMs: 10000,
    jitterFactor: 0.1
  }
});
```

**High-Availability:**

```typescript
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY,
  baseUrl: process.env.GUARDLY_URL,
  timeout: 45000,
  gracefulErrorHandling: false,  // Fail fast
  retryConfig: {
    maxAttempts: 3,
    initialDelayMs: 50,
    backoffMultiplier: 2.5,
    maxDelayMs: 5000,
    jitterFactor: 0.2
  }
});
```

---

## Single Validation

### Basic Validation

```typescript
const decision = await client.validate({
  prompt: 'What is Python?',
  output: 'Python is a programming language.'
});
```

### With Context

```typescript
const decision = await client.validate({
  prompt: 'What is Python?',
  output: 'Python is a programming language.',
  context: 'Python is a high-level, interpreted, and dynamically-typed programming language.'
});
```

### With Policy

```typescript
const decision = await client.validate({
  prompt: 'Is this medication safe for pregnancy?',
  output: 'Yes, this medication is safe.',
  context: 'FDA warning: Contraindicated in pregnancy.',
  policy: 'rag_strict'  // Strict policy for medical content
});
```

### With Domain

```typescript
const decision = await client.validate({
  prompt: 'Explain quantum entanglement',
  output: 'Quantum entanglement is a phenomenon in quantum mechanics.',
  context: 'Reference material...',
  domain: 'physics'  // Domain-specific context
});
```

### With Refinement Suggestions

```typescript
const decision = await client.validate({
  prompt: 'Summarize this article',
  output: 'The article discusses AI safety.',
  context: 'Article text...',
  use_refinement: true  // Get suggested_fix if decision is "regenerate"
});

if (decision.decision === 'regenerate') {
  console.log('Suggestion:', decision.suggested_fix);
}
```

### Complete Example

```typescript
const decision = await client.validate({
  prompt: 'What are the side effects of aspirin?',
  output: 'Aspirin can cause stomach bleeding.',
  context: 'Medical literature: Aspirin increases bleeding risk in patients with ulcers.',
  policy: 'rag_strict',
  domain: 'medical',
  use_refinement: true
});

console.log(`Decision: ${decision.decision}`);
console.log(`Risk Score: ${decision.risk_score.toFixed(2)}`);
console.log(`Confidence: ${decision.confidence.toFixed(2)}`);
console.log(`Evidence: ${decision.evidence}`);
console.log(`Latency: ${decision.latency_ms?.toFixed(1)}ms`);

if (decision.tier_results) {
  decision.tier_results.forEach(tier => {
    console.log(`  ${tier.validator_name}: ${tier.score.toFixed(2)} (${tier.latency_ms?.toFixed(1)}ms)`);
  });
}
```

---

## Batch Validation

### Parallel Processing (Fastest)

```typescript
const batch = await client.batchValidate({
  requests: [
    {
      prompt: 'What is Python?',
      output: 'Python is a programming language.',
      context: 'Python is a high-level language.'
    },
    {
      prompt: 'What is Node.js?',
      output: 'Node.js is a JavaScript runtime.',
      context: 'Node.js is built on Chrome V8 engine.'
    }
  ],
  mode: 'parallel'
});

console.log(`Results: ${batch.successful_validations}/${batch.total_requests}`);
batch.results.forEach((result, i) => {
  console.log(`  [${i}] ${result.decision} (risk=${result.risk_score?.toFixed(2)})`);
});
```

### Sequential Processing (Ordered)

```typescript
const batch = await client.batchValidate({
  requests: [
    { prompt: 'Q1?', output: 'A1', context: 'C1' },
    { prompt: 'Q2?', output: 'A2', context: 'C2' },
    { prompt: 'Q3?', output: 'A3', context: 'C3' }
  ],
  mode: 'sequential',
  timeout_per_request_ms: 45000
});
```

### With Custom Timeout

```typescript
const batch = await client.batchValidate({
  requests: requests,
  mode: 'parallel',
  timeout_per_request_ms: 60000  // 60 second per-request timeout
});
```

### Complete Batch Example

```typescript
interface Document {
  id: string;
  query: string;
  answer: string;
  source: string;
}

async function validateDocuments(docs: Document[]) {
  const batch = await client.batchValidate({
    requests: docs.map(doc => ({
      prompt: doc.query,
      output: doc.answer,
      context: doc.source,
      policy: 'default'
    })),
    mode: 'parallel',
    timeout_per_request_ms: 45000
  });

  const results = new Map<string, boolean>();

  batch.results.forEach((result, index) => {
    const docId = docs[index].id;
    const isSafe = result.decision === 'allow';
    results.set(docId, isSafe);

    console.log(`[${docId}] ${isSafe ? '✓' : '✗'} ${result.decision}`);
  });

  console.log(`\nSummary:`);
  console.log(`  Total: ${batch.total_requests}`);
  console.log(`  Successful: ${batch.successful_validations}`);
  console.log(`  Failed: ${batch.failed_validations}`);
  console.log(`  Latency: ${batch.batch_latency_ms?.toFixed(1)}ms`);

  return results;
}
```

---

## Retry Configuration

### RetryConfig Interface

```typescript
interface RetryConfig {
  // Maximum number of retry attempts (including initial attempt)
  // Default: 3
  maxAttempts: number;

  // Initial delay before first retry in milliseconds
  // Default: 100
  initialDelayMs: number;

  // Multiplier for exponential backoff
  // Example: 100ms × 2 × 2 × 2 = 800ms
  // Default: 2
  backoffMultiplier: number;

  // Maximum delay between retries in milliseconds
  // Default: 10000
  maxDelayMs: number;

  // Jitter factor as decimal (0.1 = ±10%)
  // Helps avoid thundering herd problem
  // Default: 0.1
  jitterFactor: number;
}
```

### Examples

**No Retries:**

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000',
  retryConfig: {
    maxAttempts: 1  // No retries
  }
});
```

**Aggressive Retries:**

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000',
  retryConfig: {
    maxAttempts: 5,
    initialDelayMs: 50,
    backoffMultiplier: 2,
    maxDelayMs: 5000,
    jitterFactor: 0.2
  }
});
```

**Conservative Retries:**

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000',
  retryConfig: {
    maxAttempts: 3,
    initialDelayMs: 200,
    backoffMultiplier: 1.5,
    maxDelayMs: 20000,
    jitterFactor: 0.05
  }
});
```

---

## Error Handling

### Error Classes

```typescript
import {
  GuardlyError,           // Base error class
  GuardlyValidationError, // Input validation failed
  GuardlyNetworkError,    // Network error
  GuardlyApiError         // Server returned error
} from 'guardly-node-sdk';
```

### Try-Catch Pattern

```typescript
try {
  const decision = await client.validate({
    prompt: 'What is X?',
    output: 'X is Y.'
  });

  if (decision.decision === 'allow') {
    // Process output
  }
} catch (error) {
  if (error instanceof GuardlyValidationError) {
    // Input validation failed
    console.error(`Invalid input: ${error.message}`);
    console.error(`Field: ${error.field}`);
  } else if (error instanceof GuardlyNetworkError) {
    // Network connection issue
    console.error(`Network error: ${error.message}`);
  } else if (error instanceof GuardlyApiError) {
    // Server returned error
    console.error(`API error ${error.statusCode}: ${error.message}`);
  } else {
    // Unknown error
    console.error('Unknown error:', error);
  }
}
```

### GuardlyValidationError

```typescript
try {
  await client.validate({
    prompt: '', // Empty prompt
    output: 'Output'
  });
} catch (error) {
  if (error instanceof GuardlyValidationError) {
    console.log(error.message);     // "prompt is required"
    console.log(error.field);       // "prompt"
    console.log(error.reason);      // "Missing required field"
  }
}
```

### GuardlyNetworkError

```typescript
try {
  const client = new GuardlyClient({
    apiKey: 'key',
    baseUrl: 'http://unreachable-host:5000'
  });
  await client.validate({ /* ... */ });
} catch (error) {
  if (error instanceof GuardlyNetworkError) {
    console.log(error.message);     // "Connection refused"
    console.log(error.statusCode);  // undefined
  }
}
```

### GuardlyApiError

```typescript
try {
  await client.validate({
    prompt: 'What is X?',
    output: 'X is Y.',
    policy: 'nonexistent_policy'
  });
} catch (error) {
  if (error instanceof GuardlyApiError) {
    console.log(error.statusCode);  // 422
    console.log(error.message);     // "Policy not found"
    console.log(error.details);     // { field: 'policy', reason: '...' }
  }
}
```

### Graceful Error Handling

Instead of throwing, return neutral decision:

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000',
  gracefulErrorHandling: true  // Return abstain instead of throwing
});

// On error, returns { decision: 'abstain', risk_score: 0.5, ... }
const decision = await client.validate({ /* ... */ });

if (decision.decision === 'allow') {
  // Safe
} else if (decision.decision === 'abstain') {
  // Error occurred, but returning neutral decision
}
```

---

## Type Reference

### ValidationInput

```typescript
interface ValidationInput {
  // Required: Original user prompt or query
  prompt: string;

  // Required: Generated LLM output to validate
  output: string;

  // Optional: Reference context for fact-checking
  context?: string;

  // Optional: Policy name (default: "default")
  policy?: string;

  // Optional: Domain context (e.g., "medical", "finance")
  domain?: string;

  // Optional: Enable refinement/regeneration suggestions
  use_refinement?: boolean;
}
```

### ValidationDecision

```typescript
interface ValidationDecision {
  // Decision result
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';

  // Risk score from 0 (safe) to 1 (dangerous)
  risk_score: number;

  // Confidence in decision 0 to 1
  confidence: number;

  // Human-readable explanation
  evidence: string;

  // The validated output (same as input)
  output?: string;

  // Total validation latency in milliseconds
  latency_ms?: number;

  // Name of policy used
  policy_name?: string;

  // Per-validator results
  tier_results?: TierResult[];

  // Preprocessing metadata
  preprocessing_metadata?: PreprocessingMetadata;

  // Suggested fix if decision is "regenerate"
  suggested_fix?: string;
}
```

### TierResult

```typescript
interface TierResult {
  // Validator name: "heuristics", "embedding", "hhem"
  validator_name: string;

  // Score from 0 (hallucinated) to 1 (faithful)
  score: number;

  // Whether tier passed its threshold
  passed: boolean;

  // Human-readable explanation
  evidence: string;

  // Latency in milliseconds
  latency_ms: number;

  // Error message if validator failed
  error?: string;
}
```

### BatchValidationResult

```typescript
interface BatchValidationResult {
  // Unique batch identifier
  batch_id: string;

  // Total requests in batch
  total_requests: number;

  // Successful validations
  successful_validations: number;

  // Failed validations
  failed_validations: number;

  // Total batch latency
  batch_latency_ms: number;

  // Error messages
  errors: string[];

  // Per-request results
  results: BatchResultItem[];
}
```

### BatchResultItem

```typescript
interface BatchResultItem {
  // Optional request identifier
  id?: string;

  // Decision
  decision?: 'allow' | 'block' | 'regenerate' | 'abstain';

  // Risk score
  risk_score?: number;

  // Confidence
  confidence?: number;

  // Explanation
  evidence?: string;

  // Request latency
  latency_ms?: number;

  // Error message if failed
  error?: string;
}
```

---

## Best Practices

### 1. Always Provide Context When Available

```typescript
// ✓ Good
const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Western Europe. Its capital is Paris.'
});

// ✗ Less effective (no context)
const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.'
});
```

### 2. Use Domain-Specific Policies

```typescript
// ✓ Medical content: strict policy
const medicalDecision = await client.validate({
  prompt: 'Is this medicine safe?',
  output: '...',
  policy: 'rag_strict'
});

// ✓ Chatbot: low-latency policy
const chatDecision = await client.validate({
  prompt: 'Tell me a joke',
  output: '...',
  policy: 'chatbot'
});
```

### 3. Handle All Decision Types

```typescript
// ✓ Handle all outcomes
const decision = await client.validate({ /* ... */ });

switch (decision.decision) {
  case 'allow':
    // Safe to return
    return decision.output;
  case 'block':
    // Reject output
    throw new Error('Output blocked by safety check');
  case 'regenerate':
    // Retry generation
    console.log('Hint:', decision.suggested_fix);
    return await regenerateWithHint(decision.suggested_fix);
  case 'abstain':
    // Unable to determine
    return decision.output;  // Return as-is or fail
}
```

### 4. Monitor Latency

```typescript
const startTime = Date.now();
const decision = await client.validate({ /* ... */ });
const duration = Date.now() - startTime;

if (duration > 100) {
  console.warn(`Slow validation: ${duration}ms`);
}
```

### 5. Batch Large Workloads

```typescript
// ✓ Batch processing
const batch = await client.batchValidate({
  requests: manyRequests,
  mode: 'parallel'  // Much faster than sequential calls
});

// ✗ Individual validations (inefficient)
for (const req of manyRequests) {
  const decision = await client.validate(req);
}
```

### 6. Configure Appropriate Timeouts

```typescript
// For real-time APIs (e.g., chatbots)
const realtimeClient = new GuardlyClient({
  timeout: 30000,  // 30 second timeout
  retryConfig: { maxAttempts: 1 }  // No retries
});

// For batch processing
const batchClient = new GuardlyClient({
  timeout: 120000,  // 2 minute timeout
  retryConfig: { maxAttempts: 3 }  // Allow retries
});
```

### 7. Log Decisions for Auditing

```typescript
async function validateAndLog(input: ValidationInput) {
  const decision = await client.validate(input);

  // Log for auditing/monitoring
  console.log({
    timestamp: new Date(),
    decision: decision.decision,
    risk_score: decision.risk_score,
    prompt_length: input.prompt.length,
    output_length: input.output.length,
    policy: input.policy || 'default'
  });

  return decision;
}
```

### 8. Use Environment Variables

```typescript
// ✓ Configuration from environment
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!,
  baseUrl: process.env.GUARDLY_URL || 'http://localhost:5000',
  timeout: parseInt(process.env.GUARDLY_TIMEOUT || '30000'),
  gracefulErrorHandling: process.env.NODE_ENV === 'production'
});
```

---

## Examples

### Real-time Chat Validation

```typescript
app.post('/api/chat', async (req, res) => {
  const { message } = req.body;
  const response = await llm.generate(message);

  const decision = await client.validate({
    prompt: message,
    output: response,
    policy: 'chatbot'
  });

  res.json({
    response: decision.decision === 'allow' ? response : 'Unable to answer',
    safe: decision.decision === 'allow'
  });
});
```

### Document Processing

```typescript
async function processBatch(documents: string[]) {
  const batch = await client.batchValidate({
    requests: documents.map(doc => ({
      prompt: 'Summarize this',
      output: summarize(doc),
      context: doc
    })),
    mode: 'parallel'
  });

  return batch.results.map(r => r.decision === 'allow');
}
```

For more examples, see [EXAMPLES.md](../EXAMPLES.md).
