/**
 * Tier-specific validation result from the hallucination detection pipeline
 */
export interface TierResult {
  /** Name of the validator tier (e.g., "heuristics", "embedding", "hhem") */
  validator_name: string;
  /** Score from 0 (hallucinated) to 1 (faithful) */
  score: number;
  /** Whether this tier passed its threshold */
  passed: boolean;
  /** Human-readable explanation of the result */
  evidence: string;
  /** Latency in milliseconds */
  latency_ms: number;
  /** Error message if the validator failed */
  error?: string;
}

/**
 * Preprocessing metadata from prompt analysis
 */
export interface PreprocessingMetadata {
  /** Detected task or query intent */
  core_task?: string;
  /** Named entities extracted from the prompt */
  entities?: string[];
  /** Context requirements inferred from the prompt */
  context_requirements?: string[];
  /** Constraints mentioned in the prompt */
  constraints?: string[];
  /** Whether fast mode was used (skip expensive validators) */
  fast_mode_applied?: boolean;
  [key: string]: any;
}

/**
 * Decision result from the hallucination detection validation
 */
export interface ValidationDecision {
  /** Decision: allow (safe), block (hallucination), regenerate (retry), abstain (insufficient data) */
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';
  /** Risk score from 0 (safe) to 1 (dangerous) */
  risk_score: number;
  /** Confidence in the decision (0-1) */
  confidence: number;
  /** Human-readable explanation of the decision */
  evidence: string;
  /** The validated output (same as input output) */
  output?: string;
  /** Suggested fix or regeneration prompt if decision is regenerate */
  suggested_fix?: string;
  /** Per-tier validation results */
  tier_results?: TierResult[];
  /** Latency of validation in milliseconds */
  latency_ms?: number;
  /** Name of the policy used for validation */
  policy_name?: string;
  /** Preprocessing metadata from prompt analysis */
  preprocessing_metadata?: PreprocessingMetadata;
}

/**
 * Input for the hallucination detection validation
 */
export interface ValidationInput {
  /** Original user prompt or query */
  prompt: string;
  /** Generated output from the LLM to validate */
  output: string;
  /** Optional reference context for fact-checking */
  context?: string;
  /** Optional policy name (defaults to "default") */
  policy?: string;
  /** Optional domain for context-specific validation (e.g., "medical", "finance") */
  domain?: string;
  /** Optional flag to enable refinement/regeneration suggestions */
  use_refinement?: boolean;
}

/**
 * Retry configuration with exponential backoff and jitter
 */
export interface RetryConfig {
  /** Maximum number of retry attempts (defaults to 3) */
  maxAttempts: number;
  /** Initial delay in milliseconds before first retry (defaults to 100) */
  initialDelayMs: number;
  /** Multiplier for exponential backoff (defaults to 2) */
  backoffMultiplier: number;
  /** Maximum delay in milliseconds between retries (defaults to 10000) */
  maxDelayMs: number;
  /** Jitter factor as a decimal (0.1 = ±10%, defaults to 0.1) */
  jitterFactor: number;
}

/**
 * Request for batch validation
 */
export interface BatchValidationRequest {
  /** Array of validation requests (must be 1-100 items) */
  requests: ValidationInput[];
  /** Processing mode: 'parallel' for concurrent validation, 'sequential' for ordered processing (defaults to 'parallel') */
  mode?: 'parallel' | 'sequential';
  /** Timeout per individual request in milliseconds (defaults to 30000, range: 1000-120000) */
  timeout_per_request_ms?: number;
}

/**
 * Individual result item in batch validation response
 */
export interface BatchResultItem {
  /** Optional request identifier for tracking */
  id?: string;
  /** Decision: allow, block, regenerate, or abstain */
  decision?: 'allow' | 'block' | 'regenerate' | 'abstain';
  /** Risk score from 0 (safe) to 1 (dangerous) */
  risk_score?: number;
  /** Confidence in the decision (0-1) */
  confidence?: number;
  /** Human-readable explanation of the decision */
  evidence?: string;
  /** Validation latency in milliseconds */
  latency_ms?: number;
  /** Error message if validation failed */
  error?: string;
}

/**
 * Response from batch validation
 */
export interface BatchValidationResult {
  /** Unique batch identifier for tracking */
  batch_id: string;
  /** Total number of requests in the batch */
  total_requests: number;
  /** Count of successful validations */
  successful_validations: number;
  /** Count of failed validations */
  failed_validations: number;
  /** Array of validation results */
  results: BatchResultItem[];
  /** Total latency for the batch in milliseconds */
  batch_latency_ms: number;
  /** Array of error messages encountered during batch processing */
  errors: string[];
}

/**
 * Configuration for the Guardly client
 */
export interface GuardlyClientConfig {
  /** API key for authentication */
  apiKey: string;
  /** Base URL of the Guardly API (defaults to http://localhost:5000) */
  baseUrl?: string;
  /** Timeout in milliseconds for API requests (defaults to 30000) */
  timeout?: number;
  /** Return neutral "abstain" decision on network error instead of throwing */
  gracefulErrorHandling?: boolean;
  /** User-Agent header override (for tracking SDK usage) */
  userAgent?: string;
  /** Optional retry configuration for network errors and transient failures */
  retryConfig?: RetryConfig;
}
