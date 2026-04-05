# guardly-node-sdk

Professional Node.js SDK for LLM hallucination detection via the Guardly REST API.

A lightweight, zero-dependency SDK that wraps the Guardly REST API for validating LLM-generated outputs against reference context. Detects hallucinations using a three-tier validation pipeline (heuristics → embeddings → HHEM classifier) with optional graceful error handling.

## Features

- ✅ **Type-Safe**: Full TypeScript support with strict type checking
- ✅ **Zero Dependencies**: Uses native Node.js fetch API (18+)
- ✅ **Lightweight**: ~5KB minified, no external packages
- ✅ **Resilient**: Custom error handling with graceful degradation option
- ✅ **Well-Documented**: Comprehensive JSDoc and examples
- ✅ **Modern**: ESM/CJS dual support, async/await patterns
- ✅ **Tested**: 15+ test cases covering all scenarios

## Installation

```bash
npm install guardly-node-sdk
```

## Quick Start

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!,
  baseUrl: 'http://localhost:5000'
});

const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Western Europe. Its capital is Paris.'
});

if (decision.decision === 'allow') {
  console.log('✓ Output is safe (risk:', decision.risk_score, ')');
} else if (decision.decision === 'block') {
  console.log('✗ Hallucination detected (risk:', decision.risk_score, ')');
} else if (decision.decision === 'regenerate') {
  console.log('↻ Try regenerating with hint:', decision.suggested_fix);
} else {
  console.log('? Insufficient data to decide (abstain)');
}
```

## API Reference

### `GuardlyClient`

#### Constructor

```typescript
const client = new GuardlyClient({
  apiKey: string;
  baseUrl?: string;                    // Default: http://localhost:5000
  timeout?: number;                    // Default: 30000ms
  gracefulErrorHandling?: boolean;     // Default: false
  userAgent?: string;                  // Custom User-Agent header
});
```

#### Methods

##### `validate(input: ValidationInput): Promise<ValidationDecision>`

Validate an LLM output for hallucinations.

**Parameters:**
```typescript
interface ValidationInput {
  prompt: string;           // Original user prompt
  output: string;           // LLM-generated output to validate
  context?: string;         // Optional reference context for fact-checking
  policy?: string;          // Policy name (default: "default")
  domain?: string;          // Domain for context-specific validation
  use_refinement?: boolean; // Enable regeneration suggestions
}
```

**Returns:**
```typescript
interface ValidationDecision {
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';
  risk_score: number;              // 0-1, where 1 = high risk
  confidence: number;              // 0-1
  evidence: string;                // Explanation of decision
  output?: string;                 // Original output
  suggested_fix?: string;          // Hint if decision === 'regenerate'
  tier_results?: TierResult[];      // Per-validator results
  latency_ms?: number;             // Validation latency
  policy_name?: string;            // Policy used
  preprocessing_metadata?: Record<string, any>;
}
```

**Example:**
```typescript
const decision = await client.validate({
  prompt: 'What year was the Titanic built?',
  output: 'The Titanic was built in 1912.',
  context: 'The Titanic was launched on May 31, 1911 and sank in 1912.'
});

console.log(decision.decision);      // 'allow' or 'block' or 'regenerate' or 'abstain'
console.log(decision.risk_score);    // e.g. 0.1 (low risk)
console.log(decision.evidence);      // "Output matches context with high confidence"
```

##### `healthCheck(): Promise<boolean>`

Check if the Guardly API is healthy and accessible.

```typescript
const isHealthy = await client.healthCheck();
if (!isHealthy) {
  console.warn('Guardly API is unavailable');
}
```

##### `getVersion(): Promise<string>`

Get the version of the Guardly API.

```typescript
const version = await client.getVersion();
console.log('API version:', version);
```

## Error Handling

The SDK throws meaningful errors for different failure scenarios:

### `GuardlyValidationError`

Thrown when input validation fails (missing/invalid fields).

```typescript
try {
  await client.validate({
    prompt: '',     // Error: prompt is required
    output: 'test'
  });
} catch (error) {
  if (error instanceof GuardlyValidationError) {
    console.log('Field:', error.field);      // 'prompt'
    console.log('Details:', error.details);  // 'prompt must be a non-empty string'
  }
}
```

### `GuardlyApiError`

Thrown when the API returns an error response (4xx/5xx).

```typescript
try {
  await client.validate({...});
} catch (error) {
  if (error instanceof GuardlyApiError) {
    console.log('Status:', error.statusCode);     // 401
    console.log('Code:', error.code);             // 'INVALID_API_KEY'
    console.log('Message:', error.message);       // 'Invalid or missing API key'
    console.log('Is auth error:', error.isAuthError());  // true
  }
}
```

### `GuardlyNetworkError`

Thrown on network connectivity failures (timeout, connection refused, etc.).

```typescript
try {
  await client.validate({...});
} catch (error) {
  if (error instanceof GuardlyNetworkError) {
    console.log('Network error:', error.message);
    console.log('Original error:', error.originalError);
  }
}
```

### Graceful Error Handling

Enable graceful error handling to return a neutral "abstain" decision instead of throwing on errors:

```typescript
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!,
  gracefulErrorHandling: true  // Return abstain on any error
});

// No exception thrown, even if API is down
const decision = await client.validate({
  prompt: 'Test',
  output: 'Test output'
});

console.log(decision.decision);  // 'abstain' if error occurred
console.log(decision.evidence);  // 'Validation service unavailable...'
```

## Usage Examples

### Basic Validation

```typescript
const client = new GuardlyClient({ apiKey: 'your-api-key' });

const decision = await client.validate({
  prompt: 'How tall is Mount Everest?',
  output: 'Mount Everest is 29,032 feet (8,849 meters) tall.',
  context: 'Mount Everest is the tallest mountain in the world at 8,849 meters.'
});

if (decision.decision === 'allow') {
  return decision.output;
} else if (decision.decision === 'block') {
  throw new Error(`Hallucination detected: ${decision.evidence}`);
} else if (decision.decision === 'regenerate') {
  // Retry with hint
  console.log('Suggested fix:', decision.suggested_fix);
}
```

### With Explicit Policy

```typescript
const decision = await client.validate({
  prompt: 'Describe this medical condition',
  output: 'Severe COVID-19 causes pneumonia...',
  context: 'Medical reference text...',
  policy: 'medical_strict',      // Use stricter policy for healthcare
  domain: 'healthcare'
});
```

### With Refinement Suggestions

```typescript
const decision = await client.validate({
  prompt: 'What is X?',
  output: 'X is...',
  context: 'Reference about X',
  use_refinement: true  // Get improvement suggestions
});

if (decision.decision === 'regenerate') {
  console.log('Try this instead:', decision.suggested_fix);
}
```

### Batch Processing

```typescript
const results = await Promise.allSettled(
  outputs.map(output => client.validate({
    prompt: originalPrompt,
    output,
    context
  }))
);

const safe = results
  .filter((r): r is PromiseFulfilledResult<ValidationDecision> =>
    r.status === 'fulfilled' && r.value.decision === 'allow'
  )
  .map(r => r.value.output);
```

### With Timeout Customization

```typescript
const client = new GuardlyClient({
  apiKey: 'your-api-key',
  timeout: 60000  // 60 second timeout instead of default 30s
});
```

## Development

### Build

```bash
npm run build          # Build ESM version
npm run build:cjs      # Build CommonJS version
npm run type-check     # Type check without emitting
```

### Testing

```bash
npm run test           # Run tests (compiled)
npm run test:dev       # Run tests with tsx (no compile step)
```

### Clean

```bash
npm run clean          # Remove dist directory
```

## TypeScript

Full TypeScript support with strict type checking:

```typescript
import {
  GuardlyClient,
  ValidationInput,
  ValidationDecision,
  GuardlyApiError,
  GuardlyNetworkError,
  GuardlyValidationError
} from 'guardly-node-sdk';

const client = new GuardlyClient({ apiKey: process.env.GUARDLY_API_KEY! });

const input: ValidationInput = {
  prompt: 'Question?',
  output: 'Answer',
  context: 'Context'
};

const decision: ValidationDecision = await client.validate(input);
```

## Performance

- **Latency**: API call latency varies (typically 50-500ms depending on policy/validators)
- **Memory**: ~2KB per client instance
- **Payload size**: ~1-2KB per validation request/response
- **Network**: Uses native fetch, supports HTTP/2

## Compatibility

- **Node.js**: 18.0.0+
- **Browser**: No (server-side only)
- **Runtime**: Works in any ESM-compatible environment with fetch

## Error Handling Best Practices

1. **Always handle validation errors**: Different error types for different scenarios
2. **Use graceful degradation**: Enable graceful error handling for robustness
3. **Log context**: Include prompt/output in error logs for debugging
4. **Retry on timeout**: Network errors may be transient
5. **Monitor risk scores**: Track distribution of risk scores over time

## Troubleshooting

### "Invalid or missing API key" (401)

```typescript
// Check that GUARDLY_API_KEY is set
console.log(process.env.GUARDLY_API_KEY);  // Should not be undefined

// Ensure it's passed correctly
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!  // Non-null assertion
});
```

### Request timeout

```typescript
// Increase timeout for slow networks
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!,
  timeout: 60000  // 60 seconds
});
```

### API unreachable

```typescript
// Enable graceful error handling
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!,
  gracefulErrorHandling: true
});

// Or check health first
const isHealthy = await client.healthCheck();
if (!isHealthy) {
  console.warn('API is down, may want to fallback');
}
```

## License

MIT

## Support

For issues, questions, or contributions:
- Report bugs: Create an issue on GitHub
- Ask questions: Check documentation or open discussion
- Contribute: Submit pull requests with improvements

---

**guardly-node-sdk** - Keeping LLMs honest.
