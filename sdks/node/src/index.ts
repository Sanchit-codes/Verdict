/**
 * Guardly Node.js SDK for LLM hallucination detection
 *
 * @packageDocumentation
 *
 * A lightweight, zero-dependency SDK for integrating hallucination detection
 * into your Node.js applications. Validates LLM outputs against reference
 * context using a multi-tier validation pipeline.
 *
 * @example
 * ```typescript
 * import { GuardlyClient } from 'guardly-node-sdk';
 *
 * const client = new GuardlyClient({
 *   apiKey: process.env.VERDICT_API_KEY!,
 *   baseUrl: 'http://localhost:5000'
 * });
 *
 * const decision = await client.validate({
 *   prompt: 'What is the capital of France?',
 *   output: 'The capital of France is Paris.',
 *   context: 'France is a country in Western Europe. Its capital is Paris.'
 * });
 *
 * console.log(decision.decision); // 'allow' | 'block' | 'regenerate' | 'abstain'
 * console.log(decision.risk_score); // 0-1
 * ```
 */

// Export types
export type {
  ValidationInput,
  ValidationDecision,
  TierResult,
  PreprocessingMetadata,
  GuardlyClientConfig,
} from './types.js';

// Export client
export { GuardlyClient } from './client.js';

// Export errors
export {
  GuardlyError,
  GuardlyApiError,
  GuardlyNetworkError,
  GuardlyValidationError,
  type ApiErrorResponse,
} from './errors.js';

/**
 * Version of the SDK
 */
export const SDK_VERSION = '1.0.0';
