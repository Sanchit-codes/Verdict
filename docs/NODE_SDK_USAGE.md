# GuardlyAI Node SDK Usage Guide

The GuardlyAI Node SDK provides a TypeScript-first client for interacting with the GuardlyAI REST API. Full type safety, automatic retries, and error handling included.

---

## Installation

```bash
npm install guardly-ai
# or
yarn add guardly-ai
```

**Requirements:**
- Node.js >= 14
- TypeScript >= 4.5 (for TypeScript projects)

---

## Quick Start

```typescript
import { GuardlyClient } from 'guardly-ai';

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000'
});

// Validate a single output
const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Europe. Its capital is Paris.'
});

console.log(`Decision: ${decision.decision}`);
console.log(`Risk: ${decision.risk_score}`);
console.log(`Latency: ${decision.latency_ms}ms`);
```

---

## Configuration

```typescript
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY,  // Required
  baseUrl: process.env.GUARDLY_BASE_URL || 'http://localhost:5000',  // Optional
  timeout: 30000,                        // Request timeout in ms (default: 30000)
  maxRetries: 3,                         // Max retry attempts (default: 3)
  retryDelay: 1000,                      // Initial retry delay in ms (default: 1000)
  retryMultiplier: 2,                    // Exponential backoff multiplier (default: 2)
  logLevel: 'info'                       // Log level: 'error' | 'warn' | 'info' | 'debug' (default: 'warn')
});
```

---

## Methods

### 1. validate() - Single Validation

Validate a single AI-generated text.

**Signature:**
```typescript
validate(request: ValidateRequest): Promise<ValidationResponse>
```

**Request:**
```typescript
interface ValidateRequest {
  prompt: string;              // Required: user question/instruction
  output: string;              // Required: AI-generated response
  context?: string;            // Optional: reference material
  policy?: string;             // Optional: 'default' | 'rag_strict' | 'chatbot'
  domain?: string;             // Optional: application domain
  use_refinement?: boolean;    // Optional: enable iterative refinement
}
```

**Response:**
```typescript
interface ValidationResponse {
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';
  risk_score: number;          // 0.0 (safe) to 1.0 (hallucinated)
  confidence: number;          // 0.0 to 1.0
  evidence: string;            // Explanation of decision
  output: string;              // Original output
  suggested_fix?: string;      // Hint for regeneration (if decision === 'regenerate')
  latency_ms: number;          // Validation time
  policy_name: string;         // Policy used
  tier_results: TierResult[];  // Results from each validator
  preprocessing_metadata?: {
    prompt_tokens: number;
    output_tokens: number;
    context_tokens: number;
  };
}
```

**Example:**
```typescript
const decision = await client.validate({
  prompt: 'Summarize this article',
  output: 'The article discusses AI ethics.',
  context: 'The article covers machine learning, data privacy, and ethical AI.',
  policy: 'rag_strict',
  domain: 'research'
});

if (decision.decision === 'allow') {
  console.log(`✓ Safe to return (risk: ${decision.risk_score})`);
  return decision.output;
} else if (decision.decision === 'block') {
  console.error(`✗ Blocked (risk: ${decision.risk_score}): ${decision.evidence}`);
  throw new Error('Output validation failed');
} else if (decision.decision === 'regenerate') {
  console.log(`↻ Regenerate with hint: ${decision.suggested_fix}`);
  return regenerateWithHint(decision.suggested_fix);
}
```

---

### 2. validateBatch() - Batch Validation

Validate multiple items in parallel or sequential mode.

**Signature:**
```typescript
validateBatch(request: BatchValidateRequest): Promise<BatchValidationResponse>
```

**Request:**
```typescript
interface BatchValidateRequest {
  mode: 'parallel' | 'sequential';  // Processing mode
  policy?: string;                  // Policy for all items
  items: Array<{
    prompt: string;
    output: string;
    context?: string;
    domain?: string;
  }>;
}
```

**Response:**
```typescript
interface BatchValidationResponse {
  batch_id: string;                    // Unique batch ID (UUID)
  total_requests: number;              // Total items processed
  successful_validations: number;      // Items with successful validation
  failed_validations: number;          // Items with validation errors
  results: ValidationResponse[];       // Array of validation results
  batch_latency_ms: number;            // Total batch time
}
```

**Example - Parallel (fast):**
```typescript
const batch = await client.validateBatch({
  mode: 'parallel',
  policy: 'default',
  items: [
    { prompt: 'Q1', output: 'A1', context: 'C1' },
    { prompt: 'Q2', output: 'A2', context: 'C2' },
    { prompt: 'Q3', output: 'A3', context: 'C3' }
  ]
});

console.log(`Batch ${batch.batch_id}:`);
console.log(`  Processed: ${batch.total_requests}`);
console.log(`  Passed: ${batch.successful_validations}`);
console.log(`  Failed: ${batch.failed_validations}`);
console.log(`  Time: ${batch.batch_latency_ms}ms`);

batch.results.forEach((result, idx) => {
  console.log(`  Item ${idx}: ${result.decision} (risk: ${result.risk_score})`);
});
```

**Example - Sequential (memory-efficient):**
```typescript
const batch = await client.validateBatch({
  mode: 'sequential',
  policy: 'rag_strict',
  items: largeItemArray  // Even 1000+ items OK
});
```

---

### 3. healthCheck() - Health Status

Get API and validator health status.

**Signature:**
```typescript
healthCheck(): Promise<HealthResponse>
```

**Response:**
```typescript
interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;                  // ISO 8601 timestamp
  validators: {
    [key: string]: {
      available: boolean;
      latency_ms?: number;
    };
  };
}
```

**Example:**
```typescript
const health = await client.healthCheck();

console.log(`Status: ${health.status}`);
console.log(`Time: ${health.timestamp}`);

Object.entries(health.validators).forEach(([name, info]) => {
  const status = info.available ? '✓' : '✗';
  console.log(`  ${status} ${name}: ${info.latency_ms}ms`);
});

if (health.status === 'unhealthy') {
  throw new Error('API is unhealthy');
}
```

---

### 4. getVersion() - Version Info

Get API and SDK version information.

**Signature:**
```typescript
getVersion(): Promise<VersionResponse>
```

**Response:**
```typescript
interface VersionResponse {
  api_version: string;
  sdk_version: string;
  python_version: string;
  transformers_version: string;
  torch_version: string;
}
```

**Example:**
```typescript
const version = await client.getVersion();

console.log(`API: ${version.api_version}`);
console.log(`SDK: ${version.sdk_version}`);
console.log(`Python: ${version.python_version}`);
```

---

### 5. getPolicies() - List Policies

Get all available validation policies.

**Signature:**
```typescript
getPolicies(): Promise<Policy[]>
```

**Response:**
```typescript
interface Policy {
  name: string;
  description: string;
  risk_threshold: number;
  validators_enabled: string[];
  latency_budget_ms: number;
}
```

**Example:**
```typescript
const policies = await client.getPolicies();

policies.forEach(policy => {
  console.log(`${policy.name}: ${policy.description}`);
  console.log(`  Risk threshold: ${policy.risk_threshold}`);
  console.log(`  Latency budget: ${policy.latency_budget_ms}ms`);
  console.log(`  Validators: ${policy.validators_enabled.join(', ')}`);
});
```

---

## Error Handling

All methods throw `GuardlyError` on failure:

```typescript
try {
  const decision = await client.validate({
    prompt: 'test',
    output: 'test'
  });
} catch (error) {
  if (error instanceof GuardlyError) {
    console.error(`Code: ${error.code}`);
    console.error(`Message: ${error.message}`);
    console.error(`Status: ${error.statusCode}`);
    
    if (error.code === 'INVALID_AUTH') {
      // Invalid API key
      console.error('Check your API key');
    } else if (error.code === 'SERVICE_DEGRADED') {
      // API unavailable, retry later
      console.error('API temporarily unavailable');
    } else if (error.code === 'VALIDATION_ERROR') {
      // Request validation failed
      console.error('Request validation failed');
    }
  }
}
```

**Error Codes:**
- `INVALID_INPUT` - Malformed request
- `INVALID_AUTH` - Missing/invalid API key
- `VALIDATION_ERROR` - Schema validation failed
- `SERVICE_DEGRADED` - API unavailable
- `TIMEOUT` - Request timeout
- `NETWORK_ERROR` - Network connectivity issue

---

## Retry Configuration

Configure automatic exponential backoff retries:

```typescript
const client = new GuardlyClient({
  apiKey: 'key',
  maxRetries: 5,         // Retry up to 5 times
  retryDelay: 500,       // Start with 500ms
  retryMultiplier: 2     // Double delay each time: 500ms, 1s, 2s, 4s, 8s
});

// 503 and 429 errors auto-retry
// 400, 401, 422 errors do NOT retry
```

---

## Complete Example

```typescript
import { GuardlyClient, GuardlyError } from 'guardly-ai';

async function main() {
  const client = new GuardlyClient({
    apiKey: process.env.GUARDLY_API_KEY || 'dev-key',
    baseUrl: process.env.GUARDLY_BASE_URL || 'http://localhost:5000',
    logLevel: 'info'
  });

  try {
    // 1. Check health
    console.log('Checking API health...');
    const health = await client.healthCheck();
    console.log(`Status: ${health.status}\n`);

    // 2. Get version
    const version = await client.getVersion();
    console.log(`API v${version.api_version}, SDK v${version.sdk_version}\n`);

    // 3. List policies
    const policies = await client.getPolicies();
    console.log(`Available policies: ${policies.map(p => p.name).join(', ')}\n`);

    // 4. Single validation
    console.log('Validating single output...');
    const decision = await client.validate({
      prompt: 'What is the capital of France?',
      output: 'The capital of France is Paris.',
      context: 'France is a country in Europe. Paris is its capital city.',
      policy: 'default'
    });
    console.log(`Decision: ${decision.decision}`);
    console.log(`Risk: ${decision.risk_score.toFixed(2)}`);
    console.log(`Latency: ${decision.latency_ms.toFixed(1)}ms\n`);

    // 5. Batch validation
    console.log('Validating batch...');
    const batch = await client.validateBatch({
      mode: 'parallel',
      items: [
        { prompt: 'Q1', output: 'A1' },
        { prompt: 'Q2', output: 'A2' },
        { prompt: 'Q3', output: 'A3' }
      ]
    });
    console.log(`Batch ${batch.batch_id}:`);
    console.log(`  Total: ${batch.total_requests}`);
    console.log(`  Passed: ${batch.successful_validations}`);
    console.log(`  Failed: ${batch.failed_validations}`);
    console.log(`  Time: ${batch.batch_latency_ms.toFixed(1)}ms`);

  } catch (error) {
    if (error instanceof GuardlyError) {
      console.error(`Error: [${error.code}] ${error.message}`);
      if (error.statusCode === 503) {
        console.error('API is unavailable, retrying...');
      }
    } else {
      console.error('Unexpected error:', error);
    }
  }
}

main();
```

---

## TypeScript Usage

Full type safety with exported types:

```typescript
import {
  GuardlyClient,
  GuardlyError,
  ValidateRequest,
  ValidationResponse,
  BatchValidateRequest,
  BatchValidationResponse,
  HealthResponse,
  VersionResponse
} from 'guardly-ai';

// All methods fully typed
const client = new GuardlyClient({ apiKey: 'key' });

const decision: ValidationResponse = await client.validate({
  prompt: 'test',
  output: 'test'
});

const batch: BatchValidationResponse = await client.validateBatch({
  mode: 'parallel',
  items: [{ prompt: 'q', output: 'a' }]
});
```

---

## Environment Variables

```bash
export GUARDLY_API_KEY="your-api-key"
export GUARDLY_BASE_URL="http://localhost:5000"
export GUARDLY_LOG_LEVEL="info"
```

---

## Performance Tips

1. **Use batch validation for multiple items:**
   ```typescript
   // Good: Single request for 10 items
   await client.validateBatch({ mode: 'parallel', items: [...] });
   
   // Avoid: 10 separate requests
   for (const item of items) {
     await client.validate(item);
   }
   ```

2. **Use sequential mode for large batches (>100 items):**
   ```typescript
   // For memory efficiency
   const batch = await client.validateBatch({
     mode: 'sequential',
     items: largeArray
   });
   ```

3. **Use the chatbot policy for low-latency requirements:**
   ```typescript
   const decision = await client.validate({
     prompt: 'q',
     output: 'a',
     policy: 'chatbot'  // p95 < 50ms
   });
   ```

4. **Configure retries for reliability:**
   ```typescript
   const client = new GuardlyClient({
     apiKey: 'key',
     maxRetries: 3,
     retryDelay: 500
   });
   ```

---

## Support

- Issues: [GitHub Issues](https://github.com/guardly/guardly-ai/issues)
- REST API docs: [REST_API.md](REST_API.md)
- Deployment: [DEPLOYMENT.md](DEPLOYMENT.md)
- Python SDK: [hallucination-guard](https://github.com/guardly/hallucination-guard)
