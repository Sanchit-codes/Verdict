/**
 * useGuardly - React hook for Guardly validation
 *
 * Provides validation state management and methods for validating chat messages.
 * Handles async validation with graceful error handling and non-blocking UI updates.
 *
 * @example
 * ```tsx
 * const { isValidating, decision, error, riskScore, validate } = useGuardly();
 *
 * const handleSendMessage = async (message: string) => {
 *   const result = await validate(message, assistantOutput, context);
 *   if (result?.decision === 'allow') {
 *     displayMessage(assistantOutput);
 *   }
 * };
 * ```
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { getGuardedClient } from '@/lib/guardly-client';
import type { ValidationResult } from '@/types/guardly';

/**
 * Hook state returned by useGuardly
 */
export interface UseGuardlyState {
  isValidating: boolean;
  decision: ValidationResult['decision'] | null;
  error: string | null;
  riskScore: number | null;
  confidence: number | null;
  evidence: string | null;
  latencyMs: number | null;
}

/**
 * useGuardly - Hook for Guardly validation in React components
 *
 * @param initialApiEndpoint - Initial API endpoint (uses localStorage fallback)
 * @param initialPolicy - Initial validation policy (default: 'default')
 * @returns Object with state and validate function
 */
export function useGuardly(
  initialApiEndpoint?: string,
  initialPolicy: 'default' | 'rag_strict' | 'chatbot' = 'default'
) {
  const [state, setState] = useState<UseGuardlyState>({
    isValidating: false,
    decision: null,
    error: null,
    riskScore: null,
    confidence: null,
    evidence: null,
    latencyMs: null,
  });

  const clientRef = useRef(getGuardedClient());
  const policyRef = useRef(initialPolicy);

  // Initialize client with API endpoint if provided
  useEffect(() => {
    const client = clientRef.current;
    if (initialApiEndpoint) {
      client.setApiBaseUrl(initialApiEndpoint);
    }
  }, [initialApiEndpoint]);

  /**
   * Validate a single message
   *
   * @param prompt - User prompt or query
   * @param output - Generated assistant output
   * @param context - Optional reference context for fact-checking
   * @returns Promise resolving to the validation result, or null on error
   */
  const validate = useCallback(
    async (
      prompt: string,
      output: string,
      context?: string
    ): Promise<ValidationResult | null> => {
      setState((prev) => ({
        ...prev,
        isValidating: true,
        error: null,
        decision: null,
      }));

      try {
        const client = clientRef.current;
        const decision = await client.validateMessage(
          prompt,
          output,
          context,
          policyRef.current
        );

        // Update state with result
        setState({
          isValidating: false,
          decision: decision.decision,
          error: null,
          riskScore: decision.risk_score,
          confidence: decision.confidence,
          evidence: decision.evidence,
          latencyMs: decision.latency_ms ?? null,
        });

        return decision;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Validation failed';

        setState((prev) => ({
          ...prev,
          isValidating: false,
          error: errorMsg,
          decision: 'abstain',
          riskScore: 0.5,
          confidence: 0,
          evidence: 'Validation unavailable',
        }));

        return null;
      }
    },
    []
  );

  /**
   * Set the validation policy for subsequent validations
   */
  const setPolicy = useCallback(
    (policy: 'default' | 'rag_strict' | 'chatbot') => {
      policyRef.current = policy;
    },
    []
  );

  /**
   * Set the API endpoint for the client
   */
  const setApiEndpoint = useCallback((endpoint: string) => {
    clientRef.current.setApiBaseUrl(endpoint);
  }, []);

  /**
   * Get the current API endpoint
   */
  const getApiEndpoint = useCallback(() => {
    return clientRef.current.getApiBaseUrl();
  }, []);

  /**
   * Clear validation state
   */
  const clearState = useCallback(() => {
    setState({
      isValidating: false,
      decision: null,
      error: null,
      riskScore: null,
      confidence: null,
      evidence: null,
      latencyMs: null,
    });
  }, []);

  return {
    ...state,
    validate,
    setPolicy,
    setApiEndpoint,
    getApiEndpoint,
    clearState,
  };
}
