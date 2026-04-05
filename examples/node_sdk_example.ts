/**
 * HallucinationGuard Node.js SDK Usage Examples
 *
 * This file demonstrates all major features of the Guardly Node.js SDK:
 * - Single validation
 * - Batch validation
 * - Policy discovery
 * - Version checking
 * - Error handling
 * - Retry configuration
 *
 * Run with: npx ts-node examples/node_sdk_example.ts
 * Or compile and run: npm run build && node dist/examples/node_sdk_example.js
 */

import {
  GuardlyClient,
  GuardlyApiError,
  GuardlyNetworkError,
  GuardlyValidationError,
  ValidationInput,
  ValidationDecision,
  BatchValidationResult,
  PolicyInfo,
  VersionInfo,
} from 'guardly-node-sdk';

// Initialize client
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY || 'test-api-key',
  baseUrl: process.env.GUARDLY_BASE_URL || 'http://localhost:5000',
  timeout: 30000,
  gracefulErrorHandling: true,
  retryConfig: {
    maxRetries: 3,
    initialDelayMs: 100,
    maxDelayMs: 5000,
    backoffMultiplier: 2,
  },
});

/**
 * Example 1: Single Validation
 *
 * Validates a single LLM output for hallucinations.
 */
async function example1_singleValidation(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 1: Single Validation');
  console.log('='.repeat(60) + '\n');

  const input: ValidationInput = {
    prompt: 'What is the capital of France?',
    output: 'The capital of France is Paris.',
    context: 'France is a country in Western Europe. Its capital is Paris.',
    policy: 'default',
    domain: 'geography',
  };

  try {
    console.log('Input:');
    console.log(`  Prompt: ${input.prompt}`);
    console.log(`  Output: ${input.output}`);
    console.log(`  Context: ${input.context}`);
    console.log();

    const decision: ValidationDecision = await client.validate(input);

    console.log('Decision:');
    console.log(`  Result: ${decision.decision}`);
    console.log(`  Risk Score: ${decision.risk_score.toFixed(2)}`);
    console.log(`  Confidence: ${decision.confidence.toFixed(2)}`);
    console.log(`  Evidence: ${decision.evidence}`);
    console.log(`  Latency: ${decision.latency_ms}ms`);
    console.log(`  Policy: ${decision.policy_name}`);
  } catch (error) {
    handleError(error);
  }
}

/**
 * Example 2: Single Validation with Hallucination
 *
 * Validates output that contains a hallucination.
 */
async function example2_singleValidationWithHallucination(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 2: Single Validation with Hallucination');
  console.log('='.repeat(60) + '\n');

  const input: ValidationInput = {
    prompt: 'What does photosynthesis do?',
    output: 'Photosynthesis makes plants intelligent and able to think.',
    context:
      'Photosynthesis is the process plants use to convert light energy into chemical energy (glucose). It does not affect plant intelligence.',
    policy: 'default',
  };

  try {
    console.log('Input:');
    console.log(`  Prompt: ${input.prompt}`);
    console.log(`  Output: ${input.output}`);
    console.log();

    const decision: ValidationDecision = await client.validate(input);

    console.log('Decision:');
    console.log(`  Result: ${decision.decision}`);
    console.log(`  Risk Score: ${decision.risk_score.toFixed(2)}`);
    console.log(`  Confidence: ${decision.confidence.toFixed(2)}`);
    console.log(`  Evidence: ${decision.evidence}`);
    console.log(`  Suggested Fix: ${decision.suggested_fix || 'N/A'}`);
  } catch (error) {
    handleError(error);
  }
}

/**
 * Example 3: Batch Validation (Parallel Mode)
 *
 * Validates multiple outputs in parallel for better throughput.
 */
async function example3_batchValidation(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 3: Batch Validation (Parallel Mode)');
  console.log('='.repeat(60) + '\n');

  const inputs: ValidationInput[] = [
    {
      id: 'req_1',
      prompt: 'What is the capital of France?',
      output: 'The capital of France is Paris.',
      context: 'France is in Western Europe. Its capital is Paris.',
    },
    {
      id: 'req_2',
      prompt: 'What does photosynthesis do?',
      output: 'Photosynthesis makes plants intelligent.',
      context:
        'Photosynthesis converts light to chemical energy in plant cells.',
    },
    {
      id: 'req_3',
      prompt: 'What is the largest planet?',
      output: 'The largest planet in our solar system is Jupiter.',
      context: 'Jupiter is a gas giant and is the largest planet.',
      policy: 'default',
    },
  ];

  try {
    console.log(`Validating ${inputs.length} items in parallel...\n`);

    const result: BatchValidationResult = await client.validateBatch(inputs, {
      mode: 'parallel',
      timeout_per_request_ms: 30000,
    });

    console.log('Batch Results:');
    console.log(`  Batch ID: ${result.batch_id}`);
    console.log(
      `  Results: ${result.successful_validations}/${result.total_requests} successful`
    );
    console.log(`  Total Latency: ${result.batch_latency_ms}ms`);
    console.log();

    console.log('Individual Results:');
    for (const item of result.results) {
      if (item.error) {
        console.log(`  ${item.id}: ERROR - ${item.error}`);
      } else {
        console.log(
          `  ${item.id}: ${item.decision} (risk: ${item.risk_score?.toFixed(2)}, latency: ${item.latency_ms}ms)`
        );
      }
    }
  } catch (error) {
    handleError(error);
  }
}

/**
 * Example 4: Batch Validation (Sequential Mode)
 *
 * Validates multiple outputs sequentially for guaranteed order.
 */
async function example4_batchValidationSequential(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 4: Batch Validation (Sequential Mode)');
  console.log('='.repeat(60) + '\n');

  const inputs: ValidationInput[] = [
    {
      id: 'seq_1',
      prompt: 'Test 1',
      output: 'Output 1',
      context: 'Context 1',
    },
    {
      id: 'seq_2',
      prompt: 'Test 2',
      output: 'Output 2',
      context: 'Context 2',
    },
  ];

  try {
    console.log(`Validating ${inputs.length} items sequentially...\n`);

    const result: BatchValidationResult = await client.validateBatch(inputs, {
      mode: 'sequential',
      timeout_per_request_ms: 30000,
    });

    console.log(`Results: ${result.successful_validations}/${result.total_requests}`);
    console.log(`Latency: ${result.batch_latency_ms}ms`);
  } catch (error) {
    handleError(error);
  }
}

/**
 * Example 5: Policy Discovery
 *
 * Retrieves and displays available policies.
 */
async function example5_policyDiscovery(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 5: Policy Discovery');
  console.log('='.repeat(60) + '\n');

  try {
    const policies: PolicyInfo[] = await client.getPolicies();

    console.log(`Available Policies (${policies.length}):\n`);

    for (const policy of policies) {
      console.log(`Policy: ${policy.name}`);
      console.log(`  Description: ${policy.description}`);
      console.log(`  Risk Threshold: ${policy.risk_threshold}`);
      console.log(
        `  Validators: ${policy.validators_enabled.join(', ')}`
      );
      console.log(`  Latency Budget: ${policy.latency_budget_ms}ms`);
      console.log();
    }
  } catch (error) {
    handleError(error);
  }
}

/**
 * Example 6: Version Information
 *
 * Retrieves API and SDK version information.
 */
async function example6_versionInfo(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 6: Version Information');
  console.log('='.repeat(60) + '\n');

  try {
    const version: VersionInfo = await client.getVersion();

    console.log('Version Information:');
    console.log(`  API Version: ${version.api_version}`);
    console.log(`  SDK Version: ${version.sdk_version}`);
    console.log(`  Python: ${version.python_version}`);
    console.log(`  Transformers: ${version.transformers_version}`);
    console.log(`  Torch: ${version.torch_version}`);
    console.log(`  Policy Schema: ${version.policy_schema_version}`);
  } catch (error) {
    handleError(error);
  }
}

/**
 * Example 7: Error Handling
 *
 * Demonstrates proper error handling with specific error types.
 */
async function example7_errorHandling(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 7: Error Handling');
  console.log('='.repeat(60) + '\n');

  // Example 7a: Invalid input
  console.log('7a: Invalid Input (missing required field)\n');
  try {
    await client.validate({
      prompt: 'Test',
      output: '', // Empty output
    });
  } catch (error) {
    if (error instanceof GuardlyValidationError) {
      console.log(`  Validation Error: ${error.message}`);
      console.log(`  Field: ${error.field}`);
    }
  }

  // Example 7b: Invalid API key
  console.log('\n7b: Invalid API Key\n');
  const badClient = new GuardlyClient({
    apiKey: 'invalid-key',
    baseUrl: 'http://localhost:5000',
  });

  try {
    await badClient.validate({
      prompt: 'Test',
      output: 'Test output',
    });
  } catch (error) {
    if (error instanceof GuardlyApiError) {
      console.log(`  API Error: ${error.statusCode}`);
      console.log(`  Code: ${error.code}`);
      console.log(`  Message: ${error.message}`);
    }
  }

  // Example 7c: Network error
  console.log('\n7c: Network Error (unreachable service)\n');
  const offlineClient = new GuardlyClient({
    apiKey: 'test-key',
    baseUrl: 'http://unreachable-service:5000',
    timeout: 1000, // Short timeout
  });

  try {
    await offlineClient.validate({
      prompt: 'Test',
      output: 'Test output',
    });
  } catch (error) {
    if (error instanceof GuardlyNetworkError) {
      console.log(`  Network Error: ${error.message}`);
    }
  }
}

/**
 * Example 8: Graceful Degradation
 *
 * Shows how to handle service unavailability gracefully.
 */
async function example8_gracefulDegradation(): Promise<void> {
  console.log('\n' + '='.repeat(60));
  console.log('Example 8: Graceful Degradation');
  console.log('='.repeat(60) + '\n');

  console.log('When gracefulErrorHandling is enabled:');
  console.log(
    '  - Service errors return decision="abstain" instead of throwing'
  );
  console.log('  - Your application can continue with fallback logic\n'
  );

  const clientWithGraceful = new GuardlyClient({
    apiKey: process.env.GUARDLY_API_KEY || 'test-key',
    baseUrl: process.env.GUARDLY_BASE_URL || 'http://localhost:5000',
    gracefulErrorHandling: true, // Enable graceful fallback
  });

  try {
    const decision = await clientWithGraceful.validate({
      prompt: 'Test',
      output: 'Test output',
    });

    console.log(`Decision: ${decision.decision}`);
    if (decision.decision === 'abstain') {
      console.log('  → Service unavailable, application can implement fallback');
    }
  } catch (error) {
    // Even with gracefulErrorHandling, some errors may still throw
    console.log(`Still threw error: ${error}`);
  }
}

/**
 * Helper function to handle errors
 */
function handleError(error: unknown): void {
  if (error instanceof GuardlyApiError) {
    console.error(`❌ API Error (${error.statusCode}): ${error.code}`);
    console.error(`   Message: ${error.message}`);
    if (error.details) {
      console.error(`   Details:`, error.details);
    }
  } else if (error instanceof GuardlyNetworkError) {
    console.error(`❌ Network Error: ${error.message}`);
  } else if (error instanceof GuardlyValidationError) {
    console.error(`❌ Validation Error: ${error.message}`);
    if (error.field) {
      console.error(`   Field: ${error.field}, Constraint: ${error.constraint}`);
    }
  } else if (error instanceof Error) {
    console.error(`❌ Error: ${error.message}`);
  } else {
    console.error(`❌ Unknown error:`, error);
  }
}

/**
 * Run all examples
 */
async function runAllExamples(): Promise<void> {
  console.log('\n');
  console.log('╔═══════════════════════════════════════════════════════════╗');
  console.log('║  HallucinationGuard Node.js SDK Examples                  ║');
  console.log('╚═══════════════════════════════════════════════════════════╝');

  try {
    await example1_singleValidation();
    await example2_singleValidationWithHallucination();
    await example3_batchValidation();
    await example4_batchValidationSequential();
    await example5_policyDiscovery();
    await example6_versionInfo();
    await example7_errorHandling();
    await example8_gracefulDegradation();

    console.log('\n' + '='.repeat(60));
    console.log('✓ All examples completed');
    console.log('='.repeat(60) + '\n');
  } catch (error) {
    console.error('Fatal error:', error);
    process.exit(1);
  }
}

// Run examples
runAllExamples().catch((error) => {
  console.error('Fatal error running examples:', error);
  process.exit(1);
});
