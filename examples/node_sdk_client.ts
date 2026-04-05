/**
 * GuardlyAI Node SDK Example Client
 *
 * Demonstrates all major SDK methods with full TypeScript types and error handling.
 *
 * USAGE:
 *   npx tsx examples/node_sdk_client.ts
 *
 * ENVIRONMENT VARIABLES:
 *   GUARDLY_API_KEY   Your API key (required)
 *   GUARDLY_BASE_URL  API base URL (default: http://localhost:5000)
 */

import { GuardlyClient, GuardlyError } from 'guardly-ai';

/**
 * Main application entry point
 */
async function main(): Promise<void> {
  // =========================================================================
  // Configuration
  // =========================================================================

  const apiKey = process.env.GUARDLY_API_KEY;
  if (!apiKey) {
    console.error('❌ GUARDLY_API_KEY environment variable not set');
    console.error('   Set your API key: export GUARDLY_API_KEY="your-key"');
    process.exit(1);
  }

  const baseUrl = process.env.GUARDLY_BASE_URL || 'http://localhost:5000';

  // =========================================================================
  // Client Initialization
  // =========================================================================

  console.log('🚀 Initializing GuardlyAI client...\n');

  const client = new GuardlyClient({
    apiKey,
    baseUrl,
    timeout: 30000,
    maxRetries: 3,
    retryDelay: 1000,
    logLevel: 'info'
  });

  try {
    // =====================================================================
    // 1. Health Check
    // =====================================================================

    console.log('📊 Checking API health...');
    const health = await client.healthCheck();
    console.log(`   Status: ${health.status}`);
    console.log(`   Timestamp: ${health.timestamp}`);
    console.log('   Validators:');
    Object.entries(health.validators).forEach(([name, info]) => {
      const status = info.available ? '✓' : '✗';
      const latency = info.latency_ms ? ` (${info.latency_ms.toFixed(1)}ms)` : '';
      console.log(`     ${status} ${name}${latency}`);
    });
    console.log('');

    // =====================================================================
    // 2. Version Information
    // =====================================================================

    console.log('📦 Fetching version information...');
    const version = await client.getVersion();
    console.log(`   API: v${version.api_version}`);
    console.log(`   SDK: v${version.sdk_version}`);
    console.log(`   Python: v${version.python_version}`);
    console.log(`   Transformers: v${version.transformers_version}`);
    console.log(`   PyTorch: v${version.torch_version}`);
    console.log('');

    // =====================================================================
    // 3. List Available Policies
    // =====================================================================

    console.log('🎯 Available policies:');
    const policies = await client.getPolicies();
    policies.forEach((policy) => {
      console.log(`   • ${policy.name}`);
      console.log(`     Description: ${policy.description}`);
      console.log(`     Risk threshold: ${policy.risk_threshold}`);
      console.log(`     Latency budget: ${policy.latency_budget_ms}ms`);
      console.log(`     Validators: ${policy.validators_enabled.join(', ')}`);
    });
    console.log('');

    // =====================================================================
    // 4. Single Validation - Success Case
    // =====================================================================

    console.log('✅ Example 1: Valid output (should be allowed)');
    const validDecision = await client.validate({
      prompt: 'What is the capital of France?',
      output: 'The capital of France is Paris.',
      context: 'France is a country in Europe. Paris is its capital city.',
      policy: 'default',
      domain: 'geography'
    });
    console.log(`   Decision: ${validDecision.decision}`);
    console.log(`   Risk score: ${validDecision.risk_score.toFixed(3)}`);
    console.log(`   Confidence: ${validDecision.confidence.toFixed(3)}`);
    console.log(`   Evidence: ${validDecision.evidence}`);
    console.log(`   Latency: ${validDecision.latency_ms.toFixed(2)}ms`);
    console.log('');

    // =====================================================================
    // 5. Single Validation - Hallucination Case
    // =====================================================================

    console.log('⚠️  Example 2: Hallucinated output (should be blocked)');
    const invalidDecision = await client.validate({
      prompt: 'What is the capital of France?',
      output: 'The capital of France is Tokyo, Japan.',
      context: 'France is a country in Europe. Paris is its capital city.',
      policy: 'default'
    });
    console.log(`   Decision: ${invalidDecision.decision}`);
    console.log(`   Risk score: ${invalidDecision.risk_score.toFixed(3)}`);
    console.log(`   Evidence: ${invalidDecision.evidence}`);
    console.log('');

    // =====================================================================
    // 6. Single Validation - With Strict Policy
    // =====================================================================

    console.log('🔒 Example 3: Strict policy (healthcare domain)');
    const strictDecision = await client.validate({
      prompt: 'What are the side effects of aspirin?',
      output: 'Aspirin can cause bleeding and gastrointestinal issues.',
      context:
        'Aspirin is a pain reliever. Common side effects include gastrointestinal bleeding, rash, and bruising.',
      policy: 'rag_strict',
      domain: 'healthcare'
    });
    console.log(`   Decision: ${strictDecision.decision}`);
    console.log(`   Risk score: ${strictDecision.risk_score.toFixed(3)}`);
    console.log(`   Policy: ${strictDecision.policy_name}`);
    console.log('');

    // =====================================================================
    // 7. Batch Validation - Parallel Mode
    // =====================================================================

    console.log('⚡ Example 4: Batch validation (parallel mode - fast)');
    const batchParallel = await client.validateBatch({
      mode: 'parallel',
      policy: 'default',
      items: [
        {
          prompt: 'What is the capital of France?',
          output: 'The capital of France is Paris.',
          context: 'France is in Europe. Paris is its capital.'
        },
        {
          prompt: 'What is the capital of Germany?',
          output: 'The capital of Germany is Berlin.',
          context: 'Germany is in Europe. Berlin is its capital.'
        },
        {
          prompt: 'What is the capital of Japan?',
          output: 'The capital of Japan is Tokyo.',
          context: 'Japan is in Asia. Tokyo is its capital city.'
        }
      ]
    });
    console.log(`   Batch ID: ${batchParallel.batch_id}`);
    console.log(`   Total: ${batchParallel.total_requests}`);
    console.log(`   Passed: ${batchParallel.successful_validations}`);
    console.log(`   Failed: ${batchParallel.failed_validations}`);
    console.log(`   Latency: ${batchParallel.batch_latency_ms.toFixed(2)}ms`);
    console.log('   Results:');
    batchParallel.results.forEach((result, idx) => {
      const icon = result.decision === 'allow' ? '✓' : '✗';
      console.log(`     ${icon} Item ${idx + 1}: ${result.decision} (risk: ${result.risk_score.toFixed(3)})`);
    });
    console.log('');

    // =====================================================================
    // 8. Batch Validation - Sequential Mode
    // =====================================================================

    console.log('🔄 Example 5: Batch validation (sequential mode - memory efficient)');
    const batchSequential = await client.validateBatch({
      mode: 'sequential',
      policy: 'chatbot', // Low-latency policy
      items: [
        { prompt: 'Q1', output: 'A1' },
        { prompt: 'Q2', output: 'A2' }
      ]
    });
    console.log(`   Mode: sequential`);
    console.log(`   Total: ${batchSequential.total_requests}`);
    console.log(`   Latency: ${batchSequential.batch_latency_ms.toFixed(2)}ms`);
    console.log('');

    // =====================================================================
    // 9. Validator Tier Results
    // =====================================================================

    console.log('📈 Example 6: Detailed tier results');
    const detailedDecision = await client.validate({
      prompt: 'What is machine learning?',
      output: 'Machine learning is a subset of AI that learns patterns from data.',
      context:
        'Machine learning uses algorithms to learn patterns without explicit programming. AI is broader and includes reasoning, planning, and more.',
      policy: 'default'
    });

    console.log(`   Decision: ${detailedDecision.decision}`);
    console.log(`   Tier Results:`);
    detailedDecision.tier_results.forEach((result) => {
      const status = result.passed ? '✓' : '✗';
      console.log(`     ${status} ${result.validator_name}`);
      console.log(`        Score: ${result.score.toFixed(3)}`);
      console.log(`        Latency: ${result.latency_ms.toFixed(2)}ms`);
      console.log(`        Evidence: ${result.evidence}`);
    });
    console.log('');

    // =====================================================================
    // 10. Minimal Request (optional fields)
    // =====================================================================

    console.log('🎯 Example 7: Minimal request (only required fields)');
    const minimalDecision = await client.validate({
      prompt: 'What is 2+2?',
      output: '2+2=4'
      // context, policy, domain are optional
    });
    console.log(`   Decision: ${minimalDecision.decision}`);
    console.log(`   Risk: ${minimalDecision.risk_score.toFixed(3)}`);
    console.log('');

    // =====================================================================
    // Summary
    // =====================================================================

    console.log('✅ All examples completed successfully!');
    console.log('');
    console.log('📖 Next steps:');
    console.log('   • Check REST API docs: https://github.com/guardly/guardly-ai/blob/main/docs/REST_API.md');
    console.log('   • Check SDK docs: https://github.com/guardly/guardly-ai/blob/main/docs/NODE_SDK_USAGE.md');
    console.log('   • Deploy to production: See DEPLOYMENT.md');
    console.log('');

  } catch (error) {
    // =========================================================================
    // Error Handling
    // =========================================================================

    if (error instanceof GuardlyError) {
      console.error(`❌ GuardlyError: [${error.code}] ${error.message}`);
      console.error(`   Status Code: ${error.statusCode}`);

      // Handle specific error codes
      if (error.code === 'INVALID_AUTH') {
        console.error('   → Check your API key: export GUARDLY_API_KEY="your-key"');
      } else if (error.code === 'SERVICE_DEGRADED') {
        console.error('   → API is temporarily unavailable, check health endpoint');
      } else if (error.code === 'VALIDATION_ERROR') {
        console.error('   → Request validation failed, check required fields');
      } else if (error.code === 'TIMEOUT') {
        console.error('   → Request timeout, increase timeout setting');
      } else if (error.code === 'NETWORK_ERROR') {
        console.error(`   → Network error, check API URL: ${baseUrl}`);
      }
    } else if (error instanceof Error) {
      console.error(`❌ Error: ${error.message}`);
      console.error(error.stack);
    } else {
      console.error('❌ Unknown error:', error);
    }

    process.exit(1);
  }
}

// ============================================================================
// Execute
// ============================================================================

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
