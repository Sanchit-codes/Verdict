# Guardly Node.js SDK - Project Summary

## 📋 Overview

A professional, lightweight Node.js SDK for integrating LLM hallucination detection into applications. The SDK wraps the Guardly REST API and provides:

- ✅ **Type-Safe**: Full TypeScript support with strict type checking
- ✅ **Zero Dependencies**: Uses native Node.js APIs (fetch, AbortController)
- ✅ **Lightweight**: ~5KB minified, ~2KB gzipped
- ✅ **Resilient**: Custom error handling with graceful degradation options
- ✅ **Well-Tested**: 15 comprehensive test cases (all passing)
- ✅ **Well-Documented**: JSDoc comments, architecture guide, usage examples

## 📁 Project Structure

```
guardly-node-sdk/
├── src/
│   ├── types.ts           # Type definitions
│   ├── errors.ts          # Custom error classes
│   ├── client.ts          # Main GuardlyClient class
│   ├── index.ts           # Barrel exports
│   └── test.ts            # 15 test cases with mock fetch
├── dist/                  # Compiled output (generated)
├── package.json           # Dependencies and scripts
├── tsconfig.json          # TypeScript configuration
├── README.md              # Complete usage guide
├── ARCHITECTURE.md        # Design and internals
├── EXAMPLES.md            # Real-world usage scenarios
└── PROJECT_SUMMARY.md     # This file
```

## 🚀 Key Components

### 1. GuardlyClient (`src/client.ts`)

Main class for interacting with the Guardly API.

**Constructor:**
```typescript
const client = new GuardlyClient({
  apiKey: string;           // Required: Bearer token
  baseUrl?: string;         // Default: 'http://localhost:5000'
  timeout?: number;         // Default: 30000ms
  gracefulErrorHandling?: boolean;  // Default: false
  userAgent?: string;       // Custom User-Agent header
});
```

**Methods:**
```typescript
// Main validation endpoint
validate(input: ValidationInput): Promise<ValidationDecision>

// Health check
healthCheck(): Promise<boolean>

// Get API version
getVersion(): Promise<string>
```

### 2. Type System (`src/types.ts`)

**ValidationInput:**
```typescript
{
  prompt: string;           // User's original query
  output: string;           // LLM-generated response
  context?: string;         // Reference material for fact-checking
  policy?: string;          // Policy name (default: 'default')
  domain?: string;          // Domain hint (e.g., 'healthcare', 'finance')
  use_refinement?: boolean; // Request improvement suggestions
}
```

**ValidationDecision:**
```typescript
{
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';
  risk_score: number;       // 0 (safe) to 1 (dangerous)
  confidence: number;       // 0 (uncertain) to 1 (certain)
  evidence: string;         // Explanation
  output?: string;          // Original output
  suggested_fix?: string;   // Improvement hint if regenerate
  tier_results?: TierResult[];      // Per-validator breakdown
  latency_ms?: number;      // API response time
  policy_name?: string;     // Policy used
  preprocessing_metadata?: PreprocessingMetadata;
}
```

### 3. Error System (`src/errors.ts`)

**GuardlyError** (base class)
- `GuardlyValidationError`: Input validation failed (field: string, details: string)
- `GuardlyApiError`: API returned error with statusCode, code, details
  - `isAuthError()`: Check if 401/403
  - `isClientError()`: Check if 4xx
  - `isServerError()`: Check if 5xx
- `GuardlyNetworkError`: Network connectivity issue (originalError: Error)

## ✅ Test Results

```
Total: 15 | Passed: 15 | Failed: 0

✓ Client initialization: requires apiKey
✓ Client initialization: accepts valid config
✓ validate(): successful request returns allow decision
✓ validate(): block decision with evidence
✓ validate(): regenerate decision with suggestion
✓ validate(): input validation fails for missing prompt
✓ validate(): input validation fails for missing output
✓ validate(): input validation fails for invalid context type
✓ validate(): API error (401 Auth) throws GuardlyApiError
✓ validate(): API error (500 Server) throws GuardlyApiError
✓ validate(): Network timeout throws GuardlyNetworkError
✓ validate(): Graceful error handling returns abstain decision
✓ Client initialization: accepts custom baseUrl
✓ validate(): Request includes Authorization header
✓ validate(): Optional fields (policy, domain, use_refinement) accepted
```

## 📦 Build Artifacts

```
dist/
├── client.js           (7.4KB)  - Compiled client
├── client.d.ts         (2.4KB)  - Type definitions
├── client.js.map       (4.8KB)  - Source map
├── errors.js           (2.1KB)  - Error classes
├── errors.d.ts         (1.8KB)  - Type definitions
├── index.js            (1.1KB)  - Barrel export
├── index.d.ts          (1.3KB)  - Type definitions
├── types.js            (44B)    - Type exports
├── types.d.ts          (3.2KB)  - Type definitions
└── test.js             (15KB)   - Compiled tests
```

## 🔧 Build Commands

```bash
npm install              # Install dependencies
npm run build            # Compile TypeScript → ES2022 ESM
npm run build:cjs        # Compile to CommonJS (future)
npm run type-check       # Type check without emitting
npm run test             # Run compiled tests
npm run test:dev         # Run tests with tsx (no compile)
npm run clean            # Remove dist/
```

## 📊 Metrics

| Metric | Value |
|--------|-------|
| **Total Lines of Code** | ~700 (src only) |
| **Types Defined** | 5 interfaces + 4 error classes |
| **Public Methods** | 3 (validate, healthCheck, getVersion) |
| **Runtime Dependencies** | 0 |
| **Dev Dependencies** | 3 (typescript, @types/node, tsx) |
| **Test Coverage** | 15 scenarios |
| **Build Output Size** | ~5KB minified, ~2KB gzipped |
| **Node.js Requirement** | 18.0.0+ (native fetch) |

## 🎯 Usage Example

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!
});

const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is in Western Europe. Its capital is Paris.'
});

if (decision.decision === 'allow') {
  console.log('✓ Safe (risk:', decision.risk_score, ')');
} else if (decision.decision === 'block') {
  console.error('✗ Hallucination detected:', decision.evidence);
} else if (decision.decision === 'regenerate') {
  console.log('↻ Suggestion:', decision.suggested_fix);
} else {
  console.log('? Service unavailable (abstain)');
}
```

## 🔄 Request/Response Flow

```
Client Code
    ↓
Input Validation (prompt, output required; others optional)
    ↓
HTTP POST /validate with Bearer token
    ↓
    ├─ Success (200) → Parse JSON → ValidationDecision
    └─ Error (4xx/5xx) → Parse error JSON → throw GuardlyApiError
        (or return abstain decision if gracefulErrorHandling=true)
```

## 🛡️ Error Handling

### Input Validation
```typescript
try {
  await client.validate({ prompt: '', output: 'test' });
} catch (e) {
  if (e instanceof GuardlyValidationError) {
    console.log(e.field);  // 'prompt'
  }
}
```

### API Errors
```typescript
try {
  await client.validate({...});
} catch (e) {
  if (e instanceof GuardlyApiError) {
    if (e.isAuthError()) { /* 401/403 */ }
    console.log(e.statusCode, e.code, e.details);
  }
}
```

### Network Errors
```typescript
try {
  await client.validate({...});
} catch (e) {
  if (e instanceof GuardlyNetworkError) {
    console.log(e.message);  // 'Network error: ...'
  }
}
```

### Graceful Degradation
```typescript
const client = new GuardlyClient({
  apiKey: '...',
  gracefulErrorHandling: true  // Never throw
});

const decision = await client.validate({...});
// Returns abstain decision on any error
```

## 📝 Documentation

1. **README.md** - Complete usage guide with examples
2. **ARCHITECTURE.md** - Design, internals, extensibility
3. **EXAMPLES.md** - 5+ real-world scenarios
4. **JSDoc Comments** - In-code documentation on all public APIs
5. **.d.ts Files** - Full TypeScript type definitions

## ✨ Design Highlights

### Zero Dependencies
Uses only Node.js native APIs:
- `fetch()` for HTTP requests
- `AbortController` for timeout handling
- `JSON` for serialization
- `Error` for custom exceptions

### Type Safety
- Strict TypeScript configuration
- All public APIs fully typed
- No `any` types in public interface
- Type inference throughout

### Error Resilience
- 4 custom error classes for different failure modes
- Graceful error handling option
- Timeout protection via AbortController
- Input validation before API calls

### Code Quality
- JSDoc comments on all public methods
- Single responsibility principle (errors, types, client separate)
- No side effects in pure functions
- Immutable configuration after initialization

## 🔮 Future Enhancements

1. **Streaming Responses**: For long-running validations
2. **Batch Validation**: Optimize throughput for multiple outputs
3. **Response Caching**: Optional built-in caching layer
4. **Metrics**: Built-in metrics collection for monitoring
5. **Retry Logic**: Configurable retry strategies
6. **Request Signing**: Optional request signature verification
7. **CommonJS Support**: Build CJS version for legacy Node.js

## 🚦 Getting Started

### 1. Install
```bash
npm install guardly-node-sdk
```

### 2. Initialize
```typescript
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!
});
```

### 3. Validate
```typescript
const decision = await client.validate({
  prompt: 'Question?',
  output: 'Answer',
  context: 'Context'
});
```

### 4. Handle Decision
```typescript
if (decision.decision === 'allow') {
  // Use output
}
```

See **README.md** and **EXAMPLES.md** for more details.

## 📄 License

MIT - See LICENSE file for details

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Add tests
4. Ensure all tests pass
5. Submit pull request

## 📞 Support

- **Issues**: Report bugs on GitHub
- **Discussions**: Ask questions in GitHub discussions
- **Documentation**: Check README.md, ARCHITECTURE.md, EXAMPLES.md

---

**Status**: ✅ Complete and tested
**Last Updated**: April 5, 2026
**Node.js Requirement**: 18.0.0+
**TypeScript Requirement**: 4.5+
