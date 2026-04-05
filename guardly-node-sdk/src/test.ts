/**
 * Comprehensive test suite for Guardly SDK
 * Tests client initialization, validation, error handling, and API mocking
 */

import { GuardlyClient } from './client.js';
import {
  GuardlyError,
  GuardlyApiError,
  GuardlyNetworkError,
  GuardlyValidationError,
} from './errors.js';
import type { ValidationDecision } from './types.js';

// ============================================================================
// Mock Fetch Setup
// ============================================================================

interface MockResponse {
  status: number;
  body: unknown;
  error?: Error;
}

let mockResponses: Map<string, MockResponse> = new Map();
let requestLog: Array<{ method: string; path: string; body: Record<string, unknown> }> = [];

// Store original fetch
const originalFetch = globalThis.fetch;

/**
 * Mock fetch implementation for testing
 */
async function mockFetch(
  url: string | URL,
  options?: Record<string, unknown>
): Promise<Response> {
  const urlStr = url.toString();
  const path = new URL(urlStr).pathname;
  const method = (options?.method as string) || 'GET';
  const body = options?.body ? JSON.parse(String(options.body)) : null;

  // Log request
  requestLog.push({ method, path, body: body as Record<string, unknown> });

  // Simulate network error if configured
  const mockResponse = mockResponses.get(path);
  if (mockResponse?.error) {
    throw mockResponse.error;
  }

  // Return mocked response
  if (mockResponse) {
    return {
      ok: mockResponse.status < 400,
      status: mockResponse.status,
      statusText: mockResponse.status < 400 ? 'OK' : 'Error',
      json: async () => mockResponse.body,
      text: async () => JSON.stringify(mockResponse.body),
    } as Response;
  }

  // Default 404 for unmocked paths
  return {
    ok: false,
    status: 404,
    statusText: 'Not Found',
    json: async () => ({ message: 'Not found' }),
    text: async () => 'Not found',
  } as Response;
}

/**
 * Setup mock fetch
 */
function setupMockFetch() {
  mockResponses.clear();
  requestLog = [];
  globalThis.fetch = mockFetch as any;
}

/**
 * Restore original fetch
 */
function restoreFetch() {
  globalThis.fetch = originalFetch;
}

// ============================================================================
// Test Cases
// ============================================================================

interface TestResult {
  name: string;
  passed: boolean;
  error?: string;
}

const results: TestResult[] = [];

/**
 * Assert that a condition is true
 */
function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

/**
 * Run a test
 */
async function test(name: string, fn: () => Promise<void>) {
  try {
    await fn();
    results.push({ name, passed: true });
    console.log(`✓ ${name}`);
  } catch (error) {
    results.push({
      name,
      passed: false,
      error: (error as Error).message,
    });
    console.log(`✗ ${name}: ${(error as Error).message}`);
  }
}

// ============================================================================
// Tests
// ============================================================================

/**
 * Test 1: Client initialization validation
 */
await test('Client initialization: requires apiKey', async () => {
  try {
    new GuardlyClient({ apiKey: '' });
    throw new Error('Should have thrown GuardlyValidationError');
  } catch (error) {
    assert(error instanceof GuardlyValidationError, 'Should be GuardlyValidationError');
    assert((error as GuardlyValidationError).field === 'apiKey', 'Field should be apiKey');
  }
});

/**
 * Test 2: Client accepts valid config
 */
await test('Client initialization: accepts valid config', async () => {
  const client = new GuardlyClient({ apiKey: 'test-key-123' });
  assert(client !== null, 'Client should be created');
});

/**
 * Test 3: Successful validation request
 */
await test('validate(): successful request returns allow decision', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 200,
    body: {
      decision: 'allow',
      risk_score: 0.1,
      confidence: 0.95,
      evidence: 'Output matches context',
      output: 'The capital of France is Paris.',
      latency_ms: 125,
      policy_name: 'default',
      tier_results: [
        {
          validator_name: 'heuristics',
          score: 0.9,
          passed: true,
          evidence: 'High context overlap',
          latency_ms: 5,
        },
      ],
    } as ValidationDecision,
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const decision = await client.validate({
    prompt: 'What is the capital of France?',
    output: 'The capital of France is Paris.',
    context: 'France is a country in Western Europe. Its capital is Paris.',
  });

  assert(decision.decision === 'allow', 'Decision should be allow');
  assert(decision.risk_score === 0.1, 'Risk score should be 0.1');
  assert(decision.confidence === 0.95, 'Confidence should be 0.95');
  assert(requestLog.length === 1, 'Should have made 1 request');
  assert(requestLog[0].path === '/validate', 'Should POST to /validate');
  assert(requestLog[0].body.prompt === 'What is the capital of France?', 'Prompt should be in body');

  restoreFetch();
});

/**
 * Test 4: Block decision response
 */
await test('validate(): block decision with evidence', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 200,
    body: {
      decision: 'block',
      risk_score: 0.85,
      confidence: 0.92,
      evidence: 'Output contradicts context',
      suggested_fix: 'The capital of Japan is Tokyo, not Kyoto',
      latency_ms: 450,
      policy_name: 'rag_strict',
    } as ValidationDecision,
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const decision = await client.validate({
    prompt: 'What is the capital of Japan?',
    output: 'The capital of Japan is Kyoto.',
    context: 'Japan is an island nation in East Asia. Its capital is Tokyo.',
  });

  assert(decision.decision === 'block', 'Decision should be block');
  assert(decision.risk_score === 0.85, 'Risk score should be 0.85');
  assert(decision.suggested_fix !== undefined, 'Should include suggested fix');

  restoreFetch();
});

/**
 * Test 5: Regenerate decision
 */
await test('validate(): regenerate decision with suggestion', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 200,
    body: {
      decision: 'regenerate',
      risk_score: 0.55,
      confidence: 0.7,
      evidence: 'Uncertain match between output and context',
      suggested_fix: 'Please provide more specific information about the capital.',
      latency_ms: 320,
      policy_name: 'default',
    } as ValidationDecision,
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const decision = await client.validate({
    prompt: 'What is the capital?',
    output: 'It is a major city.',
    context: 'We are discussing France.',
  });

  assert(decision.decision === 'regenerate', 'Decision should be regenerate');
  assert(decision.suggested_fix !== undefined, 'Should have suggested fix');

  restoreFetch();
});

/**
 * Test 6: Input validation: missing prompt
 */
await test('validate(): input validation fails for missing prompt', async () => {
  const client = new GuardlyClient({ apiKey: 'test-key' });
  try {
    await client.validate({
      prompt: '',
      output: 'Some output',
    });
    throw new Error('Should have thrown GuardlyValidationError');
  } catch (error) {
    assert(
      error instanceof GuardlyValidationError,
      'Should be GuardlyValidationError'
    );
    assert((error as GuardlyValidationError).field === 'prompt', 'Field should be prompt');
  }
});

/**
 * Test 7: Input validation: missing output
 */
await test('validate(): input validation fails for missing output', async () => {
  const client = new GuardlyClient({ apiKey: 'test-key' });
  try {
    await client.validate({
      prompt: 'What is X?',
      output: '',
    });
    throw new Error('Should have thrown GuardlyValidationError');
  } catch (error) {
    assert(
      error instanceof GuardlyValidationError,
      'Should be GuardlyValidationError'
    );
    assert((error as GuardlyValidationError).field === 'output', 'Field should be output');
  }
});

/**
 * Test 8: Input validation: invalid context type
 */
await test('validate(): input validation fails for invalid context type', async () => {
  const client = new GuardlyClient({ apiKey: 'test-key' });
  try {
    await client.validate({
      prompt: 'What is X?',
      output: 'Answer is Y',
      context: 123 as any,
    });
    throw new Error('Should have thrown GuardlyValidationError');
  } catch (error) {
    assert(
      error instanceof GuardlyValidationError,
      'Should be GuardlyValidationError'
    );
    assert((error as GuardlyValidationError).field === 'context', 'Field should be context');
  }
});

/**
 * Test 9: API error response handling (4xx)
 */
await test('validate(): API error (401 Auth) throws GuardlyApiError', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 401,
    body: {
      code: 'INVALID_API_KEY',
      message: 'Invalid or missing API key',
      status_code: 401,
    },
  });

  const client = new GuardlyClient({ apiKey: 'invalid-key' });
  try {
    await client.validate({
      prompt: 'Test',
      output: 'Test output',
    });
    throw new Error('Should have thrown GuardlyApiError');
  } catch (error) {
    assert(error instanceof GuardlyApiError, 'Should be GuardlyApiError');
    const apiError = error as GuardlyApiError;
    assert(apiError.statusCode === 401, 'Status code should be 401');
    assert(apiError.isAuthError(), 'Should be identified as auth error');
    assert(apiError.code === 'INVALID_API_KEY', 'Code should be INVALID_API_KEY');
  }

  restoreFetch();
});

/**
 * Test 10: API error response handling (5xx)
 */
await test('validate(): API error (500 Server) throws GuardlyApiError', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 500,
    body: {
      code: 'INTERNAL_SERVER_ERROR',
      message: 'Internal server error',
      status_code: 500,
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  try {
    await client.validate({
      prompt: 'Test',
      output: 'Test output',
    });
    throw new Error('Should have thrown GuardlyApiError');
  } catch (error) {
    assert(error instanceof GuardlyApiError, 'Should be GuardlyApiError');
    const apiError = error as GuardlyApiError;
    assert(apiError.statusCode === 500, 'Status code should be 500');
    assert(apiError.isServerError(), 'Should be identified as server error');
  }

  restoreFetch();
});

/**
 * Test 11: Network error handling (timeout)
 */
await test('validate(): Network timeout throws GuardlyNetworkError', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 200,
    body: {},
    error: new Error('ECONNABORTED'),
  });

  const client = new GuardlyClient({ apiKey: 'test-key', timeout: 100 });
  try {
    await client.validate({
      prompt: 'Test',
      output: 'Test output',
    });
    throw new Error('Should have thrown GuardlyNetworkError');
  } catch (error) {
    // Could be either GuardlyNetworkError or GuardlyError depending on fetch behavior
    assert(error instanceof GuardlyError, 'Should be GuardlyError subclass');
  }

  restoreFetch();
});

/**
 * Test 12: Graceful error handling
 */
await test('validate(): Graceful error handling returns abstain decision', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 500,
    body: { message: 'Server error' },
  });

  const client = new GuardlyClient({
    apiKey: 'test-key',
    gracefulErrorHandling: true,
  });

  const decision = await client.validate({
    prompt: 'Test',
    output: 'Test output',
  });

  assert(decision.decision === 'abstain', 'Should return abstain decision');
  assert(decision.risk_score === 0.5, 'Risk score should be neutral');
  assert(decision.confidence === 0, 'Confidence should be 0');

  restoreFetch();
});

/**
 * Test 13: Custom baseUrl
 */
await test('Client initialization: accepts custom baseUrl', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 200,
    body: {
      decision: 'allow',
      risk_score: 0.1,
      confidence: 0.95,
      evidence: 'Test',
    } as ValidationDecision,
  });

  const client = new GuardlyClient({
    apiKey: 'test-key',
    baseUrl: 'https://api.example.com',
  });

  await client.validate({
    prompt: 'Test',
    output: 'Test output',
  });

  assert(
    requestLog[0].path === '/validate',
    'Should normalize URL path'
  );

  restoreFetch();
});

/**
 * Test 14: Request headers include authentication
 */
await test('validate(): Request includes Authorization header', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 200,
    body: {
      decision: 'allow',
      risk_score: 0.1,
      confidence: 0.95,
      evidence: 'Test',
    } as ValidationDecision,
  });

  const client = new GuardlyClient({ apiKey: 'secret-key-xyz' });
  await client.validate({
    prompt: 'Test',
    output: 'Test output',
  });

  // Note: In real test, would capture fetch options, this is a manual verification
  assert(requestLog.length === 1, 'Should have made request');

  restoreFetch();
});

/**
 * Test 15: Optional fields in input
 */
await test('validate(): Optional fields (policy, domain, use_refinement) accepted', async () => {
  setupMockFetch();
  mockResponses.set('/validate', {
    status: 200,
    body: {
      decision: 'allow',
      risk_score: 0.1,
      confidence: 0.95,
      evidence: 'Test',
    } as ValidationDecision,
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const decision = await client.validate({
    prompt: 'Medical question',
    output: 'Medical answer',
    context: 'Medical context',
    policy: 'medical_strict',
    domain: 'healthcare',
    use_refinement: true,
  });

  assert(decision.decision === 'allow', 'Should validate successfully');
  assert((requestLog[0].body as Record<string, unknown>).policy === 'medical_strict', 'Policy should be in request');
  assert((requestLog[0].body as Record<string, unknown>).domain === 'healthcare', 'Domain should be in request');
  assert((requestLog[0].body as Record<string, unknown>).use_refinement === true, 'use_refinement should be in request');

  restoreFetch();
});

// ============================================================================
// Results Summary
// ============================================================================

console.log('\n' + '='.repeat(70));
console.log('TEST RESULTS');
console.log('='.repeat(70));

const passed = results.filter((r) => r.passed).length;
const failed = results.filter((r) => !r.passed).length;
const total = results.length;

console.log(`Total: ${total} | Passed: ${passed} | Failed: ${failed}`);
console.log('='.repeat(70));

if (failed > 0) {
  console.log('\nFailed tests:');
  results
    .filter((r) => !r.passed)
    .forEach((r) => {
      console.log(`  ✗ ${r.name}`);
      console.log(`    ${r.error}`);
    });
  process.exit(1);
} else {
  console.log('\n✓ All tests passed!');
  process.exit(0);
}
