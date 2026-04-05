/**
 * Type definitions for Guardly validation and chat integration
 */

/**
 * Validation decision from Guardly backend
 */
export interface ValidationResult {
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';
  risk_score: number; // 0-1
  confidence: number; // 0-1
  evidence: string;
  output?: string;
  suggested_fix?: string;
  latency_ms?: number;
  latency?: LatencyBreakdown; // Full breakdown if available
  policy_name?: string;
}

/**
 * Latency breakdown for generation and validation
 */
export interface LatencyBreakdown {
  generation_ms: number;
  validation_ms: number;
  total_ms: number;
}

/**
 * Result from generateAndValidate() call
 * Combines Gemini generation with HallucinationGuard validation
 */
export interface GenerationResult {
  generated_text: string;
  decision: 'allow' | 'block' | 'regenerate' | 'abstain';
  risk_score: number; // 0-1
  confidence: number; // 0-1
  evidence: string;
  latency: LatencyBreakdown;
  policy_name?: string;
}

/**
 * Chat message with optional validation metadata
 */
export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  validation?: ValidationResult;
  timestamp: string;
}

/**
 * Settings configuration for the application
 */
export interface GuardlySettings {
  apiEndpoint: string;
  validationPolicy: 'default' | 'rag_strict' | 'chatbot';
  validationEnabled: boolean;
}

/**
 * Health status from the backend
 */
export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version?: string;
  message?: string;
}
