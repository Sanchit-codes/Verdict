import { GuardlyNetworkError, GuardlyApiError } from './errors.js';

/**
 * Configuration for exponential backoff retry strategy
 */
export interface RetryConfig {
  /** Maximum number of retry attempts (default: 3) */
  maxAttempts: number;
  /** Initial delay in milliseconds (default: 100) */
  initialDelayMs: number;
  /** Multiplier for exponential backoff (default: 2) */
  backoffMultiplier: number;
  /** Maximum delay cap in milliseconds (default: 10000) */
  maxDelayMs: number;
  /** Jitter factor for randomization, ±jitterFactor (default: 0.1 for ±10%) */
  jitterFactor: number;
}

/**
 * Default retry configuration
 */
const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxAttempts: 3,
  initialDelayMs: 100,
  backoffMultiplier: 2,
  maxDelayMs: 10000,
  jitterFactor: 0.1,
};

/**
 * Determines if an error is retryable
 * Returns true for:
 * - GuardlyNetworkError (connectivity issues)
 * - GuardlyApiError with statusCode >= 500 (server errors)
 * - GuardlyApiError with statusCode === 429 (rate limiting)
 * Returns false for 4xx client errors (non-transient)
 */
export function isNetworkError(error: unknown): boolean {
  if (error instanceof GuardlyNetworkError) {
    return true;
  }
  if (error instanceof GuardlyApiError) {
    // Retry 5xx (server errors) and 429 (rate limit), but not other 4xx
    return error.statusCode >= 500 || error.statusCode === 429;
  }
  return false;
}

/**
 * ExponentialBackoff implements retry logic with exponential delay and jitter
 * for resilient HTTP requests
 */
export class ExponentialBackoff {
  private config: RetryConfig;
  private attempt: number = 0;

  /**
   * Create an ExponentialBackoff instance
   * @param config Partial retry configuration (merged with defaults)
   */
  constructor(config: Partial<RetryConfig> = {}) {
    this.config = { ...DEFAULT_RETRY_CONFIG, ...config };
  }

  /**
   * Execute an async function with retry logic
   * @param fn Async function to execute with retries
   * @param isRetryable Function to determine if error is retryable (default: isNetworkError)
   * @returns Promise resolving to function result
   * @throws Throws the final error if all retries are exhausted or error is non-retryable
   */
  async execute<T>(
    fn: () => Promise<T>,
    isRetryable: (error: unknown) => boolean = isNetworkError
  ): Promise<T> {
    while (this.attempt < this.config.maxAttempts) {
      try {
        return await fn();
      } catch (error) {
        // Don't retry if error is not retryable or we've exhausted attempts
        if (!isRetryable(error) || this.attempt === this.config.maxAttempts - 1) {
          throw error;
        }
        
        // Calculate delay and wait before retrying
        const delay = this.calculateDelay();
        await sleep(delay);
        this.attempt++;
      }
    }
    
    // This should not be reached due to the throw above, but as a safety net
    throw new Error('Max retry attempts exceeded');
  }

  /**
   * Calculate delay for next retry attempt
   * Formula: min(initialDelay * multiplier^attempt, maxDelay) + jitter
   * Jitter is applied as ±jitterFactor * cappedDelay
   */
  private calculateDelay(): number {
    // Calculate exponential delay: initialDelayMs * (backoffMultiplier ^ attempt)
    const baseDelay =
      this.config.initialDelayMs *
      Math.pow(this.config.backoffMultiplier, this.attempt);

    // Cap the delay at maxDelayMs
    const cappedDelay = Math.min(baseDelay, this.config.maxDelayMs);

    // Add jitter: ±jitterFactor * cappedDelay
    // Math.random() * 2 - 1 gives a value in [-1, 1]
    const jitter =
      cappedDelay *
      this.config.jitterFactor *
      (Math.random() * 2 - 1);

    // Return delay, ensuring it's never negative
    return Math.max(0, cappedDelay + jitter);
  }
}

/**
 * Sleep for a given number of milliseconds
 * Utility function for delaying between retry attempts
 * @param ms Milliseconds to sleep
 * @returns Promise that resolves after the delay
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
