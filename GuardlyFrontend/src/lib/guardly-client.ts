/**
 * Guardly Frontend API Client
 *
 * A thin HTTP wrapper around the Guardly validation API.
 * Provides graceful error handling with safe fallback decisions.
 *
 * @example
 * ```typescript
 * const client = new GuardedClient({
 *   apiBaseUrl: 'http://localhost:5000/api'
 * });
 *
 * const decision = await client.validateMessage(
 *   'What is the capital of France?',
 *   'The capital of France is Paris.',
 *   'France is in Europe with capital Paris.'
 * );
 *
 * if (decision.decision === 'allow') {
 *   console.log('✓ Safe to display');
 * }
 * ```
 */

import type {
  ValidationInput,
  ValidationDecision,
} from 'guardly-node-sdk';
import type { GenerationResult, LatencyBreakdown } from '@/types/guardly';

/**
 * Health check status response from the backend
 */
export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version?: string;
  message?: string;
}

/**
 * Configuration for the Guardly API client
 */
export interface GuardedClientConfig {
  /** Base URL of the Guardly API (e.g., http://localhost:5000/api) */
  apiBaseUrl?: string;
  /** Request timeout in milliseconds (default: 30000) */
  timeout?: number;
  /** Whether to log errors to console (default: true) */
  logErrors?: boolean;
}

/**
 * GuardedClient provides a thin HTTP wrapper around the Guardly validation API.
 *
 * It handles:
 * - HTTP request/response marshalling
 * - Network error handling with graceful fallbacks
 * - Invalid response handling
 * - User-friendly error logging
 *
 * It does NOT handle:
 * - Retry logic (delegated to React hook)
 * - Request batching (use validateBatch for multiple items)
 * - State management (delegated to React hook)
 */
export class GuardedClient {
  private readonly apiBaseUrl: string;
  private readonly timeout: number;
  private readonly logErrors: boolean;

  /**
   * Initialize a new Guardly client
   * @param config Optional configuration object
   */
  constructor(config: GuardedClientConfig = {}) {
    // Default to localhost:5000/api if not provided
    const defaultUrl = 'http://localhost:5000/api';
    
    // Try to get from localStorage if available (browser context)
    let apiBaseUrl = config.apiBaseUrl;
    if (!apiBaseUrl && typeof window !== 'undefined' && window.localStorage) {
      try {
        apiBaseUrl = localStorage.getItem('guardly_api_url') || undefined;
      } catch {
        // localStorage might not be available in some contexts
      }
    }

    this.apiBaseUrl = apiBaseUrl || defaultUrl;
    this.timeout = config.timeout ?? 30000;
    this.logErrors = config.logErrors ?? true;
  }

  /**
   * Validate a single message (prompt/output pair)
   *
   * @param prompt Original user prompt or query
   * @param output Generated LLM output to validate
   * @param context Optional reference context for fact-checking
   * @param policy Optional policy name (defaults to "default")
   * @returns Promise resolving to a ValidationDecision
   *
   * @remarks
   * This method handles HTTP errors gracefully and returns a safe fallback
   * decision if the API is unreachable or returns invalid data.
   * Network errors are logged but do not throw exceptions.
   */
  public async validateMessage(
    prompt: string,
    output: string,
    context?: string,
    policy?: string
  ): Promise<ValidationDecision> {
    const input: ValidationInput = {
      prompt,
      output,
      context,
      policy,
    };

    try {
      const decision = await this.makeRequest<ValidationDecision>(
        '/validate',
        input
      );
      return decision;
    } catch (error) {
      this.logError('Message validation failed', error);
      return this.getFallbackDecision('Network error validating message');
    }
  }

  /**
   * Validate multiple messages in a batch
   *
   * @param items Array of validation inputs
   * @param policy Optional policy name (applies to all items if specified)
   * @returns Promise resolving to an array of ValidationDecisions
   *
   * @remarks
   * If the batch request fails, returns an array of fallback decisions.
   * Individual item errors are handled gracefully.
   */
  public async validateBatch(
    items: Array<{ prompt: string; output: string; context?: string }>,
    policy?: string
  ): Promise<ValidationDecision[]> {
    const inputs: ValidationInput[] = items.map((item) => ({
      ...item,
      policy,
    }));

    try {
      const response = await this.makeRequest<{
        results: ValidationDecision[];
      }>('/validate-batch', { requests: inputs });

      // Ensure we return exactly the right number of decisions
      return response.results || inputs.map(() => this.getFallbackDecision());
    } catch (error) {
      this.logError('Batch validation failed', error);
      // Return fallback decisions for all items
      return inputs.map(() =>
        this.getFallbackDecision('Batch validation failed')
      );
    }
  }



  /**
   * Generate text with Gemini and validate in one call
   *
   * @param prompt User prompt or query
   * @param context Optional reference context for fact-checking
   * @param policy Optional policy name (defaults to "default")
   * @returns Promise resolving to a GenerationResult with generated text + validation decision
   *
   * @remarks
   * This method combines generation and validation in a single endpoint call.
   * It handles HTTP errors gracefully and returns a safe fallback result if
   * the API is unreachable or returns invalid data.
   *
   * @example
   * ```typescript
   * const result = await client.generateAndValidate(
   *   'What is the capital of France?',
   *   'France is in Europe with capital Paris.',
   *   'default'
   * );
   *
   * if (result.decision === 'allow') {
   *   console.log('✓ Generated text is safe:', result.generated_text);
   * } else if (result.decision === 'block') {
   *   console.log('✗ Hallucination detected:', result.evidence);
   * }
   * ```
   */
  public async generateAndValidate(
    prompt: string,
    context?: string,
    policy?: string
  ): Promise<GenerationResult> {
    const startTime = performance.now();

    try {
      const response = await this.makeRequest<{
        generated_text: string;
        decision: 'allow' | 'block' | 'regenerate' | 'abstain';
        risk_score: number;
        confidence: number;
        evidence: string;
        latency_ms?: { generation_ms: number; validation_ms: number; total_ms: number };
        policy_name?: string;
      }>('/generate', {
        prompt,
        context,
        policy,
      });

      // Parse latency breakdown from response, or calculate from client-side timing
      const endTime = performance.now();
      const totalClientTime = endTime - startTime;
      
      const latency: LatencyBreakdown = response.latency_ms
        ? {
            generation_ms: response.latency_ms.generation_ms,
            validation_ms: response.latency_ms.validation_ms,
            total_ms: response.latency_ms.total_ms,
          }
        : {
            // Fallback: use client-side timing
            generation_ms: totalClientTime,
            validation_ms: 0,
            total_ms: totalClientTime,
          };

      return {
        generated_text: response.generated_text,
        decision: response.decision,
        risk_score: response.risk_score,
        confidence: response.confidence,
        evidence: response.evidence,
        latency,
        policy_name: response.policy_name,
      };
    } catch (error) {
      this.logError('Generation and validation failed', error);
      // Return a safe fallback result
      return this.getFallbackGenerationResult('Network error during generation');
    }
  }
  /**
   * Check backend health status
   *
   * @returns Promise resolving to a HealthStatus object
   *
   * @remarks
   * Always returns a status object, never throws.
   * If the backend is unreachable, returns 'unhealthy' status.
   */
  public async getHealth(): Promise<HealthStatus> {
    try {
      const response = await this.makeRequest<HealthStatus>('/health', null);
      return {
        ...response,
        status: response.status || 'healthy',
        timestamp: response.timestamp || new Date().toISOString(),
      };
    } catch (error) {
      this.logError('Health check failed', error);
      return {
        status: 'unhealthy',
        timestamp: new Date().toISOString(),
        message: 'Backend unreachable',
      };
    }
  }

  /**
   * Make an HTTP request to the API
   *
   * @param endpoint API endpoint (e.g., '/validate')
   * @param body Request body (null for GET requests)
   * @returns Promise resolving to the parsed response
   * @throws Error if the response is invalid or the request fails
   * @internal
   */
  private async makeRequest<T>(
    endpoint: string,
    body: unknown
  ): Promise<T> {
    const url = `${this.apiBaseUrl}${endpoint}`;

    // Create abort controller for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        method: body === null ? 'GET' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'User-Agent': 'guardly-frontend/1.0.0',
        },
        body: body === null ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(
          `HTTP ${response.status}: ${text || response.statusText}`
        );
      }

      const data = (await response.json()) as T;
      return data;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Return a safe fallback decision when validation fails
   *
   * @param evidence Optional evidence message for the decision
   * @returns A ValidationDecision with 'abstain' decision
   * @internal
   */
  private getFallbackDecision(
    evidence = 'Unable to validate, assuming safe'
  ): ValidationDecision {
    return {
      decision: 'abstain',
      risk_score: 0.5,
      confidence: 0,
      evidence,
      latency_ms: 0,
    };
  }

  /**
   * Return a safe fallback generation result when generation or validation fails
   *
   * @param evidence Optional evidence message for the decision
   * @returns A GenerationResult with 'abstain' decision and empty text
   * @internal
   */
  private getFallbackGenerationResult(
    evidence = 'Unable to generate or validate'
  ): GenerationResult {
    return {
      generated_text: '',
      decision: 'abstain',
      risk_score: 0.5,
      confidence: 0,
      evidence,
      latency: {
        generation_ms: 0,
        validation_ms: 0,
        total_ms: 0,
      },
    };
  }


  /**
   * Log an error message to console if logging is enabled
   *
   * @param message Descriptive message for the error
   * @param error The error object or exception
   * @internal
   */
  private logError(message: string, error: unknown): void {
    if (!this.logErrors) {
      return;
    }

    const errorMsg =
      error instanceof Error ? error.message : String(error);
    console.warn(`[GuardedClient] ${message}: ${errorMsg}`);
  }

  /**
   * Update the API base URL at runtime
   *
   * @param newUrl New API base URL (e.g., http://example.com/api)
   * @remarks
   * This allows frontend settings to dynamically change the validation endpoint.
   * The new URL is stored in localStorage if available.
   */
  public setApiBaseUrl(newUrl: string): void {
    (this.apiBaseUrl as any) = newUrl;

    // Persist to localStorage for future sessions
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        localStorage.setItem('guardly_api_url', newUrl);
      } catch {
        // localStorage might not be available
      }
    }
  }

  /**
   * Get the current API base URL
   *
   * @returns The configured API base URL
   */
  public getApiBaseUrl(): string {
    return this.apiBaseUrl;
  }
}

/**
 * Create a singleton instance for use throughout the frontend
 * @internal
 */
let clientInstance: GuardedClient | null = null;

/**
 * Get or create the singleton client instance
 *
 * @param config Optional configuration for the first instantiation
 * @returns The singleton GuardedClient instance
 */
export function getGuardedClient(
  config?: GuardedClientConfig
): GuardedClient {
  if (!clientInstance) {
    clientInstance = new GuardedClient(config);
  }
  return clientInstance;
}
