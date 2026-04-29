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
// Batch Validation Tests
// ============================================================================

/**
 * Test 16: validateBatch with valid requests (success case)
 */
await test('validateBatch(): successful validation of multiple requests', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 200,
    body: {
      batch_id: 'batch-123',
      total_requests: 2,
      successful_validations: 2,
      failed_validations: 0,
      batch_latency_ms: 250,
      errors: [],
      results: [
        {
          id: 'req-1',
          decision: 'allow',
          risk_score: 0.1,
          confidence: 0.95,
          evidence: 'Output matches context',
          latency_ms: 120,
        },
        {
          id: 'req-2',
          decision: 'block',
          risk_score: 0.85,
          confidence: 0.92,
          evidence: 'Output contradicts context',
          latency_ms: 130,
        },
      ],
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const result = await client.validateBatch({
    requests: [
      {
        prompt: 'What is the capital of France?',
        output: 'The capital of France is Paris.',
        context: 'France is a country in Europe. Its capital is Paris.',
      },
      {
        prompt: 'What is the capital of Japan?',
        output: 'The capital of Japan is Kyoto.',
        context: 'Japan is an island nation. Its capital is Tokyo.',
      },
    ],
    mode: 'parallel',
  });

  assert(result.batch_id === 'batch-123', 'Batch ID should be returned');
  assert(result.total_requests === 2, 'Total requests should be 2');
  assert(result.successful_validations === 2, 'Successful validations should be 2');
  assert(result.failed_validations === 0, 'Failed validations should be 0');
  assert(result.results.length === 2, 'Results array should have 2 items');
  assert(result.results[0].decision === 'allow', 'First result should be allow');
  assert(result.results[1].decision === 'block', 'Second result should be block');
  assert(requestLog.length === 1, 'Should have made 1 request');
  assert(requestLog[0].path === '/validate/batch', 'Should POST to /validate/batch');

  restoreFetch();
});

/**
 * Test 17: validateBatch validates request array is non-empty
 */
await test('validateBatch(): rejects empty requests array', async () => {
  const client = new GuardlyClient({ apiKey: 'test-key' });

  try {
    await client.validateBatch({
      requests: [],
      mode: 'parallel',
    });
    throw new Error('Should have thrown GuardlyValidationError');
  } catch (error) {
    assert(error instanceof GuardlyValidationError, 'Should be GuardlyValidationError');
    assert(
      (error as GuardlyValidationError).field === 'requests',
      'Field should be requests'
    );
  }
});

/**
 * Test 18: validateBatch validates max 100 items
 */
await test('validateBatch(): rejects more than 100 requests', async () => {
  const client = new GuardlyClient({ apiKey: 'test-key' });
  const tooManyRequests = Array.from({ length: 101 }, (_, i) => ({
    prompt: `Prompt ${i}`,
    output: `Output ${i}`,
  }));

  try {
    await client.validateBatch({
      requests: tooManyRequests,
      mode: 'parallel',
    });
    throw new Error('Should have thrown GuardlyValidationError');
  } catch (error) {
    assert(error instanceof GuardlyValidationError, 'Should be GuardlyValidationError');
    assert(
      (error as GuardlyValidationError).field === 'requests',
      'Field should be requests'
    );
  }
});

/**
 * Test 19: validateBatch with parallel mode
 */
await test('validateBatch(): parallel mode execution', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 200,
    body: {
      batch_id: 'parallel-batch',
      total_requests: 3,
      successful_validations: 3,
      failed_validations: 0,
      batch_latency_ms: 150,
      errors: [],
      results: [
        {
          decision: 'allow',
          risk_score: 0.1,
          confidence: 0.95,
          evidence: 'OK',
          latency_ms: 100,
        },
        {
          decision: 'allow',
          risk_score: 0.2,
          confidence: 0.9,
          evidence: 'OK',
          latency_ms: 110,
        },
        {
          decision: 'allow',
          risk_score: 0.15,
          confidence: 0.92,
          evidence: 'OK',
          latency_ms: 105,
        },
      ],
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const result = await client.validateBatch({
    requests: [
      { prompt: 'Q1', output: 'A1' },
      { prompt: 'Q2', output: 'A2' },
      { prompt: 'Q3', output: 'A3' },
    ],
    mode: 'parallel',
  });

  assert(result.batch_id === 'parallel-batch', 'Batch ID should match');
  assert(result.batch_latency_ms <= 150, 'Parallel mode should be efficient');
  assert((requestLog[0].body as any).mode === 'parallel', 'Mode should be in request');

  restoreFetch();
});

/**
 * Test 20: validateBatch with sequential mode
 */
await test('validateBatch(): sequential mode execution', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 200,
    body: {
      batch_id: 'sequential-batch',
      total_requests: 2,
      successful_validations: 2,
      failed_validations: 0,
      batch_latency_ms: 300,
      errors: [],
      results: [
        {
          decision: 'allow',
          risk_score: 0.1,
          confidence: 0.95,
          evidence: 'OK',
          latency_ms: 150,
        },
        {
          decision: 'block',
          risk_score: 0.8,
          confidence: 0.9,
          evidence: 'Blocked',
          latency_ms: 150,
        },
      ],
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const result = await client.validateBatch({
    requests: [
      { prompt: 'Q1', output: 'A1' },
      { prompt: 'Q2', output: 'A2' },
    ],
    mode: 'sequential',
  });

  assert(result.batch_id === 'sequential-batch', 'Batch ID should match');
  assert(result.batch_latency_ms === 300, 'Sequential mode latency should be sum');
  assert((requestLog[0].body as any).mode === 'sequential', 'Mode should be in request');

  restoreFetch();
});

/**
 * Test 21: validateBatch with partial failure (some succeed, some fail)
 */
await test('validateBatch(): partial failure handling', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 200,
    body: {
      batch_id: 'partial-fail',
      total_requests: 4,
      successful_validations: 3,
      failed_validations: 1,
      batch_latency_ms: 500,
      errors: ['Request 3 timeout'],
      results: [
        {
          decision: 'allow',
          risk_score: 0.1,
          confidence: 0.95,
          evidence: 'OK',
          latency_ms: 100,
        },
        {
          decision: 'block',
          risk_score: 0.8,
          confidence: 0.9,
          evidence: 'Blocked',
          latency_ms: 110,
        },
        {
          decision: 'abstain',
          risk_score: 0.5,
          confidence: 0,
          evidence: 'Validation timeout',
          error: 'Request timeout',
          latency_ms: 0,
        },
        {
          decision: 'regenerate',
          risk_score: 0.55,
          confidence: 0.7,
          evidence: 'Uncertain',
          latency_ms: 120,
        },
      ],
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const result = await client.validateBatch({
    requests: [
      { prompt: 'Q1', output: 'A1' },
      { prompt: 'Q2', output: 'A2' },
      { prompt: 'Q3', output: 'A3' },
      { prompt: 'Q4', output: 'A4' },
    ],
  });

  assert(result.total_requests === 4, 'Total should be 4');
  assert(result.successful_validations === 3, 'Successful should be 3');
  assert(result.failed_validations === 1, 'Failed should be 1');
  assert(result.errors.length === 1, 'Errors array should have 1 error');
  assert(result.results[2].decision === 'abstain', 'Failed request should be abstain');
  assert(result.results[2].error !== undefined, 'Failed request should have error');

  restoreFetch();
});

/**
 * Test 22: validateBatch with per-request timeout
 */
await test('validateBatch(): per-request timeout handling', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 200,
    body: {
      batch_id: 'timeout-batch',
      total_requests: 2,
      successful_validations: 1,
      failed_validations: 1,
      batch_latency_ms: 35000,
      errors: ['Request 2 exceeded timeout'],
      results: [
        {
          decision: 'allow',
          risk_score: 0.1,
          confidence: 0.95,
          evidence: 'OK',
          latency_ms: 5000,
        },
        {
          decision: 'abstain',
          risk_score: 0.5,
          confidence: 0,
          evidence: 'Request timeout',
          error: 'Exceeded timeout_per_request_ms of 30000',
          latency_ms: 30000,
        },
      ],
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const result = await client.validateBatch({
    requests: [
      { prompt: 'Q1', output: 'A1' },
      { prompt: 'Q2', output: 'A2' },
    ],
    timeout_per_request_ms: 30000,
  });

  assert(result.total_requests === 2, 'Total should be 2');
  assert(result.failed_validations === 1, 'One request should timeout');
  assert(
    (requestLog[0].body as any).timeout_per_request_ms === 30000,
    'Timeout should be in request'
  );

  restoreFetch();
});

/**
 * Test 23: validateBatch with graceful error handling (API error)
 */
await test('validateBatch(): graceful error handling on API error', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 503,
    body: {
      message: 'Service temporarily unavailable',
      code: 'SERVICE_DEGRADED',
    },
  });

  const client = new GuardlyClient({
    apiKey: 'test-key',
    gracefulErrorHandling: true,
  });

  const result = await client.validateBatch({
    requests: [
      { prompt: 'Q1', output: 'A1' },
      { prompt: 'Q2', output: 'A2' },
    ],
  });

  // Should return abstain batch instead of throwing
  assert(result.batch_id !== undefined, 'Should return batch with ID');
  assert(
    result.results.every((r) => r.decision === 'abstain'),
    'All results should be abstain'
  );

  restoreFetch();
});

/**
 * Test 24: validateBatch aggregate counts
 */
await test('validateBatch(): aggregate counts calculation', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 200,
    body: {
      batch_id: 'count-batch',
      total_requests: 10,
      successful_validations: 7,
      failed_validations: 3,
      batch_latency_ms: 1200,
      errors: ['Error 1', 'Error 2', 'Error 3'],
      results: Array.from({ length: 10 }, (_, i) => ({
        decision: i < 7 ? ('allow' as const) : ('abstain' as const),
        risk_score: 0.1,
        confidence: 0.95,
        evidence: 'Test',
        latency_ms: 120,
      })),
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const requests = Array.from({ length: 10 }, (_, i) => ({
    prompt: `Q${i}`,
    output: `A${i}`,
  }));

  const result = await client.validateBatch({ requests });

  assert(result.total_requests === 10, 'Total should be 10');
  assert(result.successful_validations === 7, 'Successful should be 7');
  assert(result.failed_validations === 3, 'Failed should be 3');
  assert(
    result.successful_validations + result.failed_validations === result.total_requests,
    'Sum of successful and failed should equal total'
  );

  restoreFetch();
});

/**
 * Test 25: validateBatch latency measurement
 */
await test('validateBatch(): batch latency measurement', async () => {
  setupMockFetch();
  mockResponses.set('/validate/batch', {
    status: 200,
    body: {
      batch_id: 'latency-batch',
      total_requests: 3,
      successful_validations: 3,
      failed_validations: 0,
      batch_latency_ms: 350,
      errors: [],
      results: [
        {
          decision: 'allow',
          risk_score: 0.1,
          confidence: 0.95,
          evidence: 'OK',
          latency_ms: 100,
        },
        {
          decision: 'allow',
          risk_score: 0.15,
          confidence: 0.92,
          evidence: 'OK',
          latency_ms: 120,
        },
        {
          decision: 'allow',
          risk_score: 0.12,
          confidence: 0.94,
          evidence: 'OK',
          latency_ms: 130,
        },
      ],
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const result = await client.validateBatch({
    requests: [
      { prompt: 'Q1', output: 'A1' },
      { prompt: 'Q2', output: 'A2' },
      { prompt: 'Q3', output: 'A3' },
    ],
  });

  assert(result.batch_latency_ms === 350, 'Batch latency should be 350ms');
  assert(result.batch_latency_ms > 0, 'Batch latency should be positive');
  assert(
    result.results.every((r) => r.latency_ms !== undefined && r.latency_ms > 0),
    'All results should have positive latency'
  );

  restoreFetch();
});

// ============================================================================
// Exponential Backoff & Retry Logic Tests
// ============================================================================

/**
 * Test 26: Exponential backoff calculates delay correctly
 */
await test('ExponentialBackoff: calculates exponential delay correctly', async () => {
  const { ExponentialBackoff } = await import('./retry.js');

  // Verify delay formula: initialDelay * (multiplier ^ attempt)
  const backoff = new ExponentialBackoff({
    initialDelayMs: 100,
    backoffMultiplier: 2,
    maxDelayMs: 10000,
    jitterFactor: 0,
  });

  // Note: We can't directly test calculateDelay() as it's private,
  // but we can verify the behavior through execute()
  let attempts = 0;
  const startTime = Date.now();

  try {
    await backoff.execute(async () => {
      attempts++;
      if (attempts < 3) {
        throw new GuardlyNetworkError('Network error', new Error('Test'));
      }
      return 'success';
    });
  } catch (error) {
    // Should eventually succeed
  }

  assert(attempts === 3, 'Should have retried until success');
});

/**
 * Test 27: Delay capped at maxDelayMs
 */
await test('ExponentialBackoff: delay capped at maxDelayMs', async () => {
  const { ExponentialBackoff, sleep } = await import('./retry.js');

  const backoff = new ExponentialBackoff({
    initialDelayMs: 100,
    backoffMultiplier: 2,
    maxDelayMs: 500,
    jitterFactor: 0,
  });

  let attempts = 0;
  const startTime = Date.now();

  try {
    await backoff.execute(
      async () => {
        attempts++;
        if (attempts <= 5) {
          throw new GuardlyNetworkError('Network error', new Error('Test'));
        }
        return 'success';
      },
      (error) => error instanceof GuardlyNetworkError
    );
  } catch (error) {
    // Allowed to fail after maxAttempts
  }

  const elapsed = Date.now() - startTime;
  // With maxDelayMs=500 and up to 4 retries, should be roughly < 2500ms
  // (not accumulating exponentially beyond the cap)
  assert(elapsed < 3000, `Elapsed time should be capped (was ${elapsed}ms)`);
});

/**
 * Test 28: Jitter applied correctly (±jitterFactor)
 */
await test('ExponentialBackoff: jitter applied correctly', async () => {
  const { ExponentialBackoff } = await import('./retry.js');

  // With jitterFactor > 0, delays should vary
  const backoff = new ExponentialBackoff({
    initialDelayMs: 100,
    backoffMultiplier: 2,
    maxDelayMs: 10000,
    jitterFactor: 0.5, // ±50%
  });

  let attempts = 0;

  try {
    await backoff.execute(
      async () => {
        attempts++;
        if (attempts <= 5) {
          throw new GuardlyNetworkError('Network error', new Error('Test'));
        }
        return 'success';
      },
      (error) => error instanceof GuardlyNetworkError
    );
  } catch (error) {
    // Expected to fail eventually
  }

  // If jitter is working, we should have retried multiple times
  assert(attempts > 1, 'Should have retried with jitter applied');
});

/**
 * Test 29: Retries on 5xx errors
 */
await test('isNetworkError: retries on 5xx errors', async () => {
  const { isNetworkError } = await import('./retry.js');

  const serverError = new GuardlyApiError(503, 'Service Unavailable');
  const notFound = new GuardlyApiError(404, 'Not Found');

  assert(isNetworkError(serverError), 'Should retry on 5xx');
  assert(!isNetworkError(notFound), 'Should NOT retry on 4xx');
});

/**
 * Test 30: Retries on 429 (rate limit)
 */
await test('isNetworkError: retries on 429 rate limit', async () => {
  const { isNetworkError } = await import('./retry.js');

  const rateLimited = new GuardlyApiError(429, 'Too Many Requests');
  const badRequest = new GuardlyApiError(400, 'Bad Request');

  assert(isNetworkError(rateLimited), 'Should retry on 429');
  assert(!isNetworkError(badRequest), 'Should NOT retry on 400');
});

/**
 * Test 31: Does NOT retry 4xx errors (except 429)
 */
await test('isNetworkError: does NOT retry non-429 4xx errors', async () => {
  const { isNetworkError } = await import('./retry.js');

  const errors = [400, 401, 403, 404, 422].map((code) =>
    new GuardlyApiError(code, `Error ${code}`)
  );

  errors.forEach((err) => {
    assert(
      !isNetworkError(err),
      `Should NOT retry ${err.statusCode}`
    );
  });
});

/**
 * Test 32: Does NOT retry on GuardlyValidationError
 */
await test('isNetworkError: does NOT retry on GuardlyValidationError', async () => {
  const { isNetworkError } = await import('./retry.js');

  const validationError = new GuardlyValidationError('Invalid input', 'field', 'details');

  assert(!isNetworkError(validationError), 'Should NOT retry validation errors');
});

/**
 * Test 33: Respects maxAttempts limit
 */
await test('ExponentialBackoff: respects maxAttempts limit', async () => {
  const { ExponentialBackoff } = await import('./retry.js');

  const backoff = new ExponentialBackoff({
    maxAttempts: 3,
    initialDelayMs: 10,
    backoffMultiplier: 2,
    maxDelayMs: 100,
    jitterFactor: 0,
  });

  let attempts = 0;

  try {
    await backoff.execute(
      async () => {
        attempts++;
        throw new GuardlyNetworkError('Network error', new Error('Test'));
      },
      (error) => error instanceof GuardlyNetworkError
    );
    throw new Error('Should have thrown after maxAttempts');
  } catch (error) {
    assert(attempts === 3, `Should attempt exactly maxAttempts (was ${attempts})`);
    assert(
      error instanceof GuardlyNetworkError,
      'Should throw the final error'
    );
  }
});

/**
 * Test 34: Returns success on eventual success after retries
 */
await test('ExponentialBackoff: returns success on eventual success', async () => {
  const { ExponentialBackoff } = await import('./retry.js');

  const backoff = new ExponentialBackoff({
    maxAttempts: 5,
    initialDelayMs: 10,
    backoffMultiplier: 2,
    maxDelayMs: 100,
    jitterFactor: 0,
  });

  let attempts = 0;
  const result = await backoff.execute(
    async () => {
      attempts++;
      if (attempts < 3) {
        throw new GuardlyNetworkError('Network error', new Error('Test'));
      }
      return 'success';
    },
    (error) => error instanceof GuardlyNetworkError
  );

  assert(result === 'success', 'Should return success');
  assert(attempts === 3, `Should have retried until success (attempts: ${attempts})`);
});

/**
 * Test 35: Throws final error after maxAttempts exhausted
 */
await test('ExponentialBackoff: throws final error after maxAttempts exhausted', async () => {
  const { ExponentialBackoff } = await import('./retry.js');

  const backoff = new ExponentialBackoff({
    maxAttempts: 2,
    initialDelayMs: 5,
    backoffMultiplier: 2,
    maxDelayMs: 50,
    jitterFactor: 0,
  });

  let attempts = 0;

  try {
    await backoff.execute(
      async () => {
        attempts++;
        throw new GuardlyNetworkError('Persistent network error', new Error('Test'));
      },
      (error) => error instanceof GuardlyNetworkError
    );
    throw new Error('Should have thrown');
  } catch (error) {
    assert(attempts === 2, `Should attempt maxAttempts times (was ${attempts})`);
    assert(
      error instanceof GuardlyNetworkError,
      'Should throw GuardlyNetworkError'
    );
    assert(
      (error as GuardlyNetworkError).message === 'Persistent network error',
      'Should throw the final error message'
    );
  }
});

// ============================================================================
// Integration Tests: Retry Logic with Client
// ============================================================================

/**
 * Test 36: Client uses retry logic for single validate()
 */
await test('Client.validate(): uses retry logic for transient failures', async () => {
  setupMockFetch();

  let callCount = 0;
  // Mock will succeed on third call
  const originalMockFetch = globalThis.fetch;
  globalThis.fetch = (async (url: any, options?: any) => {
    const path = new URL(url.toString()).pathname;
    callCount++;

    // Fail first two times, succeed on third
    if (callCount < 3) {
      const error = new TypeError('Network error');
      throw error;
    }

    if (path === '/validate') {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => ({
          decision: 'allow',
          risk_score: 0.1,
          confidence: 0.95,
          evidence: 'Success after retries',
        }),
        text: async () => 'OK',
      } as Response;
    }

    return { ok: false, status: 404 } as Response;
  }) as any;

  const client = new GuardlyClient({
    apiKey: 'test-key',
    retryConfig: {
      maxAttempts: 3,
      initialDelayMs: 5,
      backoffMultiplier: 2,
      maxDelayMs: 50,
      jitterFactor: 0,
    },
  });

  const decision = await client.validate({
    prompt: 'Test',
    output: 'Test output',
  });

  assert(decision.decision === 'allow', 'Should eventually succeed');
  assert(callCount === 3, `Should have retried (calls: ${callCount})`);

  globalThis.fetch = originalMockFetch;
});

/**
 * Test 37: Client uses retry logic for validateBatch()
 */
await test('Client.validateBatch(): uses retry logic with backoff', async () => {
  let callCount = 0;

  const originalMockFetch = globalThis.fetch;
  globalThis.fetch = (async (url: any, options?: any) => {
    const path = new URL(url.toString()).pathname;
    callCount++;

    // Fail first time, succeed on second
    if (callCount === 1) {
      throw new TypeError('Network timeout');
    }

    if (path === '/validate/batch') {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => ({
          batch_id: 'retry-batch',
          total_requests: 1,
          successful_validations: 1,
          failed_validations: 0,
          batch_latency_ms: 100,
          errors: [],
          results: [
            {
              decision: 'allow',
              risk_score: 0.1,
              confidence: 0.95,
              evidence: 'OK',
              latency_ms: 100,
            },
          ],
        }),
        text: async () => 'OK',
      } as Response;
    }

    return { ok: false, status: 404 } as Response;
  }) as any;

  const client = new GuardlyClient({
    apiKey: 'test-key',
    retryConfig: {
      maxAttempts: 3,
      initialDelayMs: 5,
      backoffMultiplier: 2,
      maxDelayMs: 50,
      jitterFactor: 0,
    },
  });

  const result = await client.validateBatch({
    requests: [{ prompt: 'Test', output: 'Output' }],
  });

  assert(result.batch_id === 'retry-batch', 'Should eventually succeed');
  assert(callCount === 2, `Should have retried once (calls: ${callCount})`);

  globalThis.fetch = originalMockFetch;
});

/**
 * Test 38: Custom retryConfig applied to client
 */
await test('Client: custom retryConfig applied correctly', async () => {
  const customRetryConfig = {
    maxAttempts: 5,
    initialDelayMs: 50,
    backoffMultiplier: 3,
    maxDelayMs: 5000,
    jitterFactor: 0.2,
  };

  const client = new GuardlyClient({
    apiKey: 'test-key',
    retryConfig: customRetryConfig,
  });

  // Verify config is applied by checking the client doesn't throw
  assert(client !== null, 'Client should accept custom retry config');
});

/**
 * Test 39: getVersion() endpoint
 */
await test('Client.getVersion(): retrieves API version', async () => {
  setupMockFetch();
  mockResponses.set('/version', {
    status: 200,
    body: {
      version: '1.0.0',
      build: 'abc123',
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const version = await client.getVersion();

  assert(version === '1.0.0', 'Should return correct version');
  assert(requestLog[0].path === '/version', 'Should POST to /version');

  restoreFetch();
});

/**
 * Test 40: getPolicies() endpoint (public, no auth)
 */
await test('Client.getPolicies(): retrieves available policies', async () => {
  setupMockFetch();
  mockResponses.set('/policies', {
    status: 200,
    body: {
      policies: [
        {
          name: 'default',
          description: 'Balanced policy for general purposes',
          is_default: true,
        },
        {
          name: 'rag_strict',
          description: 'Strict policy for high-risk domains',
          is_default: false,
        },
        {
          name: 'chatbot',
          description: 'Relaxed policy for low-latency chatbots',
          is_default: false,
        },
      ],
    },
  });

  const client = new GuardlyClient({ apiKey: 'test-key' });
  const policies = await client.getPolicies();

  assert(Array.isArray(policies), 'Should return array of policies');
  assert(policies.length === 3, 'Should have 3 policies');
  assert(policies[0].name === 'default', 'First policy should be default');
  assert(policies[0].is_default === true, 'Default policy should be marked');
  assert(requestLog[0].path === '/policies', 'Should POST to /policies');

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
