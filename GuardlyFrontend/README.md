# Guardly Frontend

Frontend API client wrapper for the Guardly hallucination detection service.

## Installation

```bash
npm install
```

## Usage

### Basic Usage

```typescript
import { GuardedClient } from './src/lib/guardly-client.js';

const client = new GuardedClient({
  apiBaseUrl: 'http://localhost:5000/api'
});

const decision = await client.validateMessage(
  'What is the capital of France?',
  'The capital of France is Paris.',
  'France is a country in Western Europe. Its capital is Paris.'
);

if (decision.decision === 'allow') {
  console.log('✓ Output is safe to display');
} else if (decision.decision === 'block') {
  console.log('✗ Hallucination detected:', decision.evidence);
}
```

### Using the Singleton

```typescript
import { getGuardedClient } from './src/lib/guardly-client.js';

// Get the singleton instance
const client = getGuardedClient({
  apiBaseUrl: 'http://localhost:5000/api'
});

// Subsequent calls return the same instance
const sameClient = getGuardedClient();
```

### Batch Validation

```typescript
const decisions = await client.validateBatch([
  { prompt: 'What is Paris?', output: 'Paris is the capital of France', context: '...' },
  { prompt: 'What is London?', output: 'London is the capital of UK', context: '...' }
], 'default');
```

### Health Checks

```typescript
const health = await client.getHealth();
if (health.status === 'healthy') {
  console.log('Backend is healthy');
} else {
  console.log('Backend is unreachable');
}
```

## API Reference

### `GuardedClient`

The main class for validating LLM outputs.

#### Constructor

```typescript
new GuardedClient(config?: GuardedClientConfig)
```

**Options:**
- `apiBaseUrl?: string` - Base URL of the Guardly API (default: `http://localhost:5000/api`)
- `timeout?: number` - Request timeout in milliseconds (default: `30000`)
- `logErrors?: boolean` - Whether to log errors to console (default: `true`)

#### Methods

##### `validateMessage(prompt, output, context?, policy?)`

Validate a single message for hallucinations.

**Parameters:**
- `prompt: string` - Original user prompt
- `output: string` - Generated LLM output
- `context?: string` - Optional reference context for fact-checking
- `policy?: string` - Optional policy name (e.g., 'default', 'rag_strict')

**Returns:** `Promise<ValidationDecision>`

**Error Handling:** Network errors are logged and return a safe `abstain` decision.

##### `validateBatch(items, policy?)`

Validate multiple messages in a batch.

**Parameters:**
- `items: Array<{ prompt, output, context? }>` - Array of validation inputs
- `policy?: string` - Optional policy name

**Returns:** `Promise<ValidationDecision[]>`

**Error Handling:** Batch failures return fallback decisions for all items.

##### `getHealth()`

Check the backend health status.

**Returns:** `Promise<HealthStatus>`

**Error Handling:** Always returns a status object, never throws.

##### `setApiBaseUrl(newUrl)`

Update the API base URL at runtime.

**Parameters:**
- `newUrl: string` - New API base URL

**Side Effects:** Stores the URL in localStorage for persistence.

##### `getApiBaseUrl()`

Get the current API base URL.

**Returns:** `string`

## Error Handling

The client implements graceful error handling:

- **Network Errors:** Logged to console (if enabled), returns `abstain` decision
- **Invalid Responses:** Logged to console, returns `abstain` decision
- **Timeouts:** Automatically aborted after 30 seconds, returns `abstain` decision

No exceptions are thrown to the caller—validation always returns a decision.

## Type Definitions

### `HealthStatus`

```typescript
interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version?: string;
  message?: string;
}
```

### `GuardedClientConfig`

```typescript
interface GuardedClientConfig {
  apiBaseUrl?: string;
  timeout?: number;
  logErrors?: boolean;
}
```

### `ValidationDecision` (from guardly-node-sdk)

```typescript
interface ValidationDecision {
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';
  risk_score: number; // 0-1
  confidence: number; // 0-1
  evidence: string;
  output?: string;
  suggested_fix?: string;
  tier_results?: TierResult[];
  latency_ms?: number;
  policy_name?: string;
  preprocessing_metadata?: PreprocessingMetadata;
}
```

## Configuration

### From Environment

The client can read the API URL from `localStorage`:

```typescript
// In browser DevTools console:
localStorage.setItem('guardly_api_url', 'http://example.com/api');

// Next time GuardedClient is created, it will use this URL
const client = new GuardedClient();
```

### From Constructor

```typescript
const client = new GuardedClient({
  apiBaseUrl: 'http://custom-api.example.com/api'
});
```

## Development

```bash
# Type checking
npm run typecheck

# Building
npm run build

# Watch mode
npm run dev
```

## License

MIT
