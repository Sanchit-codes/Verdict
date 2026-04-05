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
}
