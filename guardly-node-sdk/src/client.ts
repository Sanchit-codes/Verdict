import {
  GuardlyClientConfig,
  ValidationInput,
  ValidationDecision,
} from './types.js';
import {
  GuardlyError,
  GuardlyApiError,
  GuardlyNetworkError,
  GuardlyValidationError,
  ApiErrorResponse,
} from './errors.js';

/**
 * Guardly Client for LLM hallucination detection
 *
 * @example
 * ```typescript
 * const client = new GuardlyClient({ apiKey: 'your-api-key' });
 * const decision = await client.validate({
 *   prompt: 'What is the capital of France?',
 *   output: 'The capital of France is Paris.',
 *   context: 'France is a country in Western Europe.'
 * });
 * if (decision.decision === 'allow') {
 *   console.log('Output is safe');
 * }
 * ```
 */
export class GuardlyClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeout: number;
  private readonly gracefulErrorHandling: boolean;
  private readonly userAgent: string;

  /**
   * Initialize a new Guardly client
   * @param config Configuration object with apiKey and optional baseUrl
   * @throws GuardlyValidationError if apiKey is missing
   */
  constructor(config: GuardlyClientConfig) {
    if (!config.apiKey || config.apiKey.trim().length === 0) {
      throw new GuardlyValidationError(
        'apiKey is required',
        'apiKey',
        'apiKey must be a non-empty string'
      );
    }

    this.apiKey = config.apiKey;
    this.baseUrl = (config.baseUrl || 'http://localhost:5000').replace(
      /\/+$/,
      ''
    );
    this.timeout = config.timeout || 30000;
    this.gracefulErrorHandling = config.gracefulErrorHandling ?? false;
    this.userAgent =
      config.userAgent || 'guardly-node-sdk/1.0.0 (Node.js ' + process.version + ')';
  }

  /**
   * Validate an LLM output for hallucinations
   *
   * @param input Validation input containing prompt, output, and optional context
   * @returns A promise that resolves to a ValidationDecision
   * @throws GuardlyApiError if the API returns an error
   * @throws GuardlyNetworkError if network connectivity fails
   * @throws GuardlyValidationError if input validation fails
   */
  public async validate(
    input: ValidationInput
  ): Promise<ValidationDecision> {
    // Validate input
    this.validateInput(input);

    try {
      const response = await this.makeRequest('/validate', input);
      return response as ValidationDecision;
    } catch (error) {
      if (this.gracefulErrorHandling) {
        console.warn(
          '[Guardly] Validation failed with graceful error handling enabled, returning abstain decision',
          error
        );
        return this.createAbstainDecision();
      }
      throw error;
    }
  }

  /**
   * Health check for the Guardly API
   * @returns true if the API is healthy and accessible
   */
  public async healthCheck(): Promise<boolean> {
    try {
      const response = (await this.makeRequest('/health', {})) as Record<string, unknown>;
      return response?.status === 'healthy';
    } catch (error) {
      return false;
    }
  }

  /**
   * Get API version information
   * @returns Version string from the API
   */
  public async getVersion(): Promise<string> {
    const response = (await this.makeRequest('/version', {})) as Record<string, unknown>;
    return (response?.version as string) || 'unknown';
  }

  /**
   * Validate input object before sending to API
   * @private
   */
  private validateInput(input: ValidationInput): void {
    if (!input.prompt || typeof input.prompt !== 'string') {
      throw new GuardlyValidationError(
        'prompt is required and must be a string',
        'prompt',
        'prompt must be a non-empty string'
      );
    }

    if (!input.output || typeof input.output !== 'string') {
      throw new GuardlyValidationError(
        'output is required and must be a string',
        'output',
        'output must be a non-empty string'
      );
    }

    if (input.context && typeof input.context !== 'string') {
      throw new GuardlyValidationError(
        'context must be a string if provided',
        'context',
        'context must be a string'
      );
    }

    if (input.policy && typeof input.policy !== 'string') {
      throw new GuardlyValidationError(
        'policy must be a string if provided',
        'policy',
        'policy must be a string'
      );
    }

    if (input.domain && typeof input.domain !== 'string') {
      throw new GuardlyValidationError(
        'domain must be a string if provided',
        'domain',
        'domain must be a string'
      );
    }

    if (
      input.use_refinement !== undefined &&
      typeof input.use_refinement !== 'boolean'
    ) {
      throw new GuardlyValidationError(
        'use_refinement must be a boolean if provided',
        'use_refinement',
        'use_refinement must be a boolean'
      );
    }
  }

  /**
   * Make an authenticated HTTP request to the Guardly API
   * @private
   */
  private async makeRequest<T = unknown>(
    path: string,
    body: unknown
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: this.buildHeaders(),
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // Handle error responses
      if (!response.ok) {
        await this.handleErrorResponse(response);
      }

      // Parse and return successful response
      const data = await response.json();
      return data as T;
    } catch (error) {
      clearTimeout(timeoutId);
      this.handleRequestError(error);
      // This line is unreachable but TypeScript needs it for type inference
      throw error;
    }
  }

  /**
   * Build request headers with authentication
   * @private
   */
  private buildHeaders(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${this.apiKey}`,
      'User-Agent': this.userAgent,
      'X-SDK-Version': '1.0.0',
      'X-SDK-Language': 'nodejs',
    };
  }

  /**
   * Handle error responses from the API
   * @private
   */
  private async handleErrorResponse(response: Response): Promise<never> {
    let errorBody: unknown;
    try {
      errorBody = await response.json();
    } catch {
      errorBody = null;
    }

    const apiError = errorBody as ApiErrorResponse | null;
    const message = apiError?.message || response.statusText || 'Unknown error';
    const code = apiError?.code;
    const details = apiError?.details;

    throw new GuardlyApiError(response.status, message, code, details);
  }

  /**
   * Handle network and other request errors
   * @private
   */
  private handleRequestError(error: unknown): never {
    if (error instanceof TypeError) {
      // Network error or invalid URL
      throw new GuardlyNetworkError(
        `Network error: ${(error as Error).message}`,
        error as Error
      );
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      // Request timeout
      throw new GuardlyNetworkError(
        `Request timeout after ${this.timeout}ms`,
        error as Error
      );
    }

    if (error instanceof GuardlyError) {
      throw error;
    }

    // Unexpected error
    throw new GuardlyError(
      `Unexpected error: ${(error as Error)?.message || String(error)}`
    );
  }

  /**
   * Create a neutral abstain decision for graceful error handling
   * @private
   */
  private createAbstainDecision(): ValidationDecision {
    return {
      decision: 'abstain',
      risk_score: 0.5,
      confidence: 0,
      evidence:
        'Validation service unavailable. Decision deferred due to graceful error handling.',
      output: undefined,
      latency_ms: 0,
      policy_name: 'unknown',
    };
  }
}
