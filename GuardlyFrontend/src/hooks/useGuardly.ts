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
import type { ValidationResult, GenerationResult } from '@/types/guardly';

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
  isGenerating: boolean;
  generationLatencyMs: number | null;
  validationLatencyMs: number | null;
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
    isGenerating: false,
    generationLatencyMs: null,
    validationLatencyMs: null,
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
          isGenerating: false,
          decision: decision.decision,
          error: null,
          riskScore: decision.risk_score,
          confidence: decision.confidence,
          evidence: decision.evidence,
          latencyMs: decision.latency_ms ?? null,
          generationLatencyMs: null,
          validationLatencyMs: null,
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
   * Generate text with Gemini and validate it
   *
   * @param prompt - User prompt or query
   * @param context - Optional reference context for fact-checking
   * @returns Promise resolving to the generation result with validation, or null on error
   *
   * @remarks
   * This method combines generation and validation in a single API call.
   * It updates the hook state with generation/validation latencies and decision.
   */
  const generateAndValidate = useCallback(
    async (
      prompt: string,
      context?: string
    ): Promise<GenerationResult | null> => {
      setState((prev) => ({
        ...prev,
        isGenerating: true,
        error: null,
        decision: null,
        generationLatencyMs: null,
        validationLatencyMs: null,
      }));

      try {
        const client = clientRef.current;
        const result = await client.generateAndValidate(
          prompt,
          context,
          policyRef.current
        );

        // Update state with result
        setState({
          isValidating: false,
          isGenerating: false,
          decision: result.decision,
          error: null,
          riskScore: result.risk_score,
          confidence: result.confidence,
          evidence: result.evidence,
          latencyMs: result.latency.total_ms,
          generationLatencyMs: result.latency.generation_ms,
          validationLatencyMs: result.latency.validation_ms,
        });

        return result;
      } catch (err) {
        const errorMsg =
          err instanceof Error ? err.message : 'Generation failed';

        setState((prev) => ({
          ...prev,
          isGenerating: false,
          error: errorMsg,
          decision: 'abstain',
          riskScore: 0.5,
          confidence: 0,
          evidence: 'Generation unavailable',
          generationLatencyMs: null,
          validationLatencyMs: null,
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
      isGenerating: false,
      generationLatencyMs: null,
      validationLatencyMs: null,
    });
  }, []);

  return {
    ...state,
    validate,
    generateAndValidate,
    setPolicy,
    setApiEndpoint,
    getApiEndpoint,
    clearState,
  };
}
