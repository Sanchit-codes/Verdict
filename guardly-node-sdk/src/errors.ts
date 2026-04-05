/**
 * Base error class for all Guardly SDK errors
 */
export class GuardlyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GuardlyError';
    Object.setPrototypeOf(this, GuardlyError.prototype);
  }
}

/**
 * API error response from the Guardly server
 */
export interface ApiErrorResponse {
  /** Error code (e.g., "INVALID_INPUT", "AUTH_FAILED") */
  code?: string;
  /** Human-readable error message */
  message: string;
  /** Additional error details */
  details?: Record<string, any>;
  /** HTTP status code that triggered the error */
  status_code?: number;
}

/**
 * Error thrown when the Guardly API returns an error response
 */
export class GuardlyApiError extends GuardlyError {
  /** HTTP status code */
  public readonly statusCode: number;
  /** Error code from API */
  public readonly code?: string;
  /** Additional error details */
  public readonly details?: Record<string, any>;

  constructor(
    statusCode: number,
    message: string,
    code?: string,
    details?: Record<string, any>
  ) {
    super(message);
    this.name = 'GuardlyApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
    Object.setPrototypeOf(this, GuardlyApiError.prototype);
  }

  /**
   * Check if this is a client error (4xx)
   */
  public isClientError(): boolean {
    return this.statusCode >= 400 && this.statusCode < 500;
  }

  /**
   * Check if this is a server error (5xx)
   */
  public isServerError(): boolean {
    return this.statusCode >= 500;
  }

  /**
   * Check if this is an auth error (401/403)
   */
  public isAuthError(): boolean {
    return this.statusCode === 401 || this.statusCode === 403;
  }
}

/**
 * Error thrown on network/connection issues
 */
export class GuardlyNetworkError extends GuardlyError {
  /** Original error that caused the network failure */
  public readonly originalError: Error;

  constructor(message: string, originalError: Error) {
    super(message);
    this.name = 'GuardlyNetworkError';
    this.originalError = originalError;
    Object.setPrototypeOf(this, GuardlyNetworkError.prototype);
  }
}

/**
 * Error thrown when request validation fails
 */
export class GuardlyValidationError extends GuardlyError {
  /** Field that failed validation */
  public readonly field?: string;
  /** Validation error details */
  public readonly details?: string;

  constructor(message: string, field?: string, details?: string) {
    super(message);
    this.name = 'GuardlyValidationError';
    this.field = field;
    this.details = details;
    Object.setPrototypeOf(this, GuardlyValidationError.prototype);
  }
}
