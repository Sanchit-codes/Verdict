/**
 * Utility functions for the Guardly SDK
 */

/**
 * Sleep for a given number of milliseconds
 * Useful for delaying between retries or rate limiting
 * @param ms Milliseconds to sleep
 * @returns Promise that resolves after the specified delay
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Generate a random delay within a range
 * Useful for staggering concurrent requests or adding jitter to backoff
 * @param minMs Minimum delay in milliseconds
 * @param maxMs Maximum delay in milliseconds
 * @returns Random delay between minMs and maxMs (inclusive)
 */
export function randomDelay(minMs: number, maxMs: number): number {
  return minMs + Math.random() * (maxMs - minMs);
}

/**
 * Add jitter to a delay value
 * Jitter is applied as ±jitterFactor * delay
 * @param delay Base delay value
 * @param jitterFactor Jitter percentage (e.g., 0.1 for ±10%)
 * @returns Delay with jitter applied
 */
export function addJitter(delay: number, jitterFactor: number): number {
  const jitter = delay * jitterFactor * (Math.random() * 2 - 1);
  return Math.max(0, delay + jitter);
}

/**
 * Calculate exponential backoff delay
 * Formula: initialDelay * (multiplier ^ attempt)
 * @param attempt Current attempt number (0-indexed)
 * @param initialDelay Initial delay in milliseconds
 * @param multiplier Backoff multiplier (typically 2)
 * @param maxDelay Maximum delay cap
 * @returns Calculated delay, capped at maxDelay
 */
export function calculateExponentialDelay(
  attempt: number,
  initialDelay: number,
  multiplier: number,
  maxDelay: number
): number {
  const baseDelay = initialDelay * Math.pow(multiplier, attempt);
  return Math.min(baseDelay, maxDelay);
}

/**
 * Check if a value is a promise-like object
 * @param value Value to check
 * @returns true if value is a Promise-like object
 */
export function isPromise(value: unknown): boolean {
  return (
    value !== null &&
    typeof value === 'object' &&
    typeof (value as Promise<unknown>).then === 'function'
  );
}

/**
 * Get a human-readable time duration string
 * @param ms Milliseconds
 * @returns Formatted duration string (e.g., "1.5s", "250ms")
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Retry an async operation with exponential backoff
 * This is a convenience wrapper around the ExponentialBackoff class
 * @param fn Async function to execute
 * @param maxAttempts Maximum number of attempts
 * @param initialDelay Initial delay in milliseconds
 * @param multiplier Backoff multiplier
 * @returns Promise resolving to function result
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  maxAttempts: number = 3,
  initialDelay: number = 100,
  multiplier: number = 2
): Promise<T> {
  let lastError: Error | undefined;
  
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      
      if (attempt < maxAttempts - 1) {
        const delay = calculateExponentialDelay(
          attempt,
          initialDelay,
          multiplier,
          10000
        );
        await sleep(delay);
      }
    }
  }
  
  throw lastError || new Error('Operation failed after max retries');
}
