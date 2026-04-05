# HallucinationGuard Examples

Real-world examples and use cases for integrating HallucinationGuard into your LLM application.

## Table of Contents

1. [Example 1: Simple Chat Message Validation](#example-1-simple-chat-message-validation)
2. [Example 2: Batch Processing Documents](#example-2-batch-processing-documents)
3. [Example 3: RAG System Integration](#example-3-rag-system-integration-with-langchain)
4. [Example 4: Custom Retry Logic and Timeouts](#example-4-custom-retry-logic-and-timeouts)
5. [Example 5: Error Handling and Recovery](#example-5-error-handling-and-recovery)
6. [Example 6: Monitoring, Logging, and Observability](#example-6-monitoring-logging-and-observability)

---

## Example 1: Simple Chat Message Validation

Validate chatbot responses in real-time before returning to users.

### Setup

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000'
});
```

### Code

```typescript
async function validateChatMessage(userMessage: string, botResponse: string): Promise<string> {
  try {
    // Validate the bot's response
    const decision = await client.validate({
      prompt: userMessage,
      output: botResponse,
      policy: 'chatbot'  // Low-latency policy
    });

    // Handle decision
    if (decision.decision === 'allow') {
      console.log('✓ Safe to return to user');
      return botResponse;
    } else if (decision.decision === 'block') {
      console.log(`✗ Blocked: ${decision.evidence}`);
      return 'I cannot confidently answer that question.';
    } else if (decision.decision === 'regenerate') {
      console.log('↻ May need regeneration:', decision.suggested_fix);
      // In production, would trigger model regeneration
      return 'Let me reconsider that answer...';
    } else {
      // abstain - confidence too low
      return `I'm not certain about that: ${decision.evidence}`;
    }
  } catch (error) {
    console.error('Validation error:', error);
    // Fallback for validation failure
    return botResponse;
  }
}

// Usage
const response = await validateChatMessage(
  'What is the Earth made of?',
  'The Earth is made of rocks, metals, and water.'
);
console.log(response);
```

### Real-world Integration

In an Express.js chatbot:

```typescript
import express from 'express';
import { GuardlyClient } from 'guardly-node-sdk';

const app = express();
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY,
  baseUrl: process.env.GUARDLY_URL
});

app.post('/chat', async (req, res) => {
  const { message } = req.body;

  // Get LLM response
  const llmResponse = await generateWithGemini(message);

  // Validate before returning
  const decision = await client.validate({
    prompt: message,
    output: llmResponse,
    policy: 'chatbot'
  });

  if (decision.decision === 'allow') {
    res.json({ response: llmResponse, safe: true });
  } else {
    res.json({
      response: 'I cannot answer that with confidence.',
      safe: false,
      reason: decision.evidence
    });
  }
});

app.listen(3000);
```

---

## Example 2: Batch Processing Documents

Process many documents efficiently in parallel.

### Setup (Same as Example 1)

### Code

```typescript
interface Document {
  id: string;
  query: string;
  summary: string;
  sourceText: string;
}

async function validateDocuments(documents: Document[]): Promise<Map<string, boolean>> {
  const results = new Map<string, boolean>();

  try {
    // Prepare batch request
    const batchRequest = documents.map((doc, index) => ({
      id: `doc_${index}`,
      prompt: doc.query,
      output: doc.summary,
      context: doc.sourceText,
      policy: 'default'
    }));

    // Process in parallel mode (faster)
    const batch = await client.batchValidate({
      requests: batchRequest,
      mode: 'parallel',
      timeout_per_request_ms: 45000
    });

    // Collect results
    batch.results.forEach((result, index) => {
      const docId = documents[index].id;
      results.set(docId, result.decision === 'allow');

      if (result.decision === 'block') {
        console.log(`[${docId}] ✗ BLOCKED: ${result.evidence}`);
      } else if (result.decision === 'allow') {
        console.log(`[${docId}] ✓ ALLOWED (risk=${result.risk_score?.toFixed(2)})`);
      }
    });

    // Report stats
    const allowed = Array.from(results.values()).filter(v => v).length;
    console.log(`\nResults: ${allowed}/${documents.length} safe (${(allowed / documents.length * 100).toFixed(1)}%)`);

    if (batch.errors.length > 0) {
      console.error('Errors during batch processing:', batch.errors);
    }

  } catch (error) {
    console.error('Batch validation failed:', error);
  }

  return results;
}

// Usage
const docs: Document[] = [
  {
    id: 'doc_1',
    query: 'What are the effects of climate change?',
    summary: 'Climate change causes global warming, rising sea levels, and extreme weather.',
    sourceText: 'Source: UN Climate Report 2024...'
  },
  {
    id: 'doc_2',
    query: 'How does photosynthesis work?',
    summary: 'Plants convert sunlight into chemical energy through photosynthesis.',
    sourceText: 'Source: Biology Textbook...'
  },
  // ... more documents
];

const safeDocuments = await validateDocuments(docs);
```

### Production Version with Error Recovery

```typescript
async function validateDocumentsWithRetry(
  documents: Document[],
  maxRetries: number = 2
): Promise<Map<string, { safe: boolean; attempts: number }>> {
  const results = new Map<string, { safe: boolean; attempts: number }>();
  let remainingDocs = documents;
  let attempt = 0;

  while (attempt < maxRetries && remainingDocs.length > 0) {
    attempt++;
    console.log(`\n=== Attempt ${attempt} ===`);
    console.log(`Processing ${remainingDocs.length} documents...`);

    try {
      const batch = await client.batchValidate({
        requests: remainingDocs.map((doc, idx) => ({
          prompt: doc.query,
          output: doc.summary,
          context: doc.sourceText
        })),
        mode: 'parallel',
        timeout_per_request_ms: attempt === 1 ? 30000 : 60000
      });

      // Process successful results
      const failedDocuments: Document[] = [];
      batch.results.forEach((result, index) => {
        const docId = remainingDocs[index].id;
        if (result.error) {
          failedDocuments.push(remainingDocs[index]);
          console.log(`[${docId}] ⚠ ERROR: ${result.error}`);
        } else {
          results.set(docId, {
            safe: result.decision === 'allow',
            attempts: attempt
          });
          console.log(
            `[${docId}] ${result.decision === 'allow' ? '✓' : '✗'} ${result.decision}`
          );
        }
      });

      remainingDocs = failedDocuments;

    } catch (error) {
      console.error(`Attempt ${attempt} failed:`, error);
      if (attempt < maxRetries) {
        console.log(`Retrying ${remainingDocs.length} documents...`);
        await new Promise(resolve => setTimeout(resolve, 1000 * attempt)); // Exponential backoff
      }
    }
  }

  return results;
}
```

---

## Example 3: RAG System Integration with LangChain

Validate RAG outputs at generation time.

### Setup

```typescript
import { GuardlyClient } from 'guardly-node-sdk';
import { Document } from 'langchain/document';
import { RetrievalQA } from 'langchain/chains';

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000',
  gracefulErrorHandling: true  // Don't crash on validation failure
});
```

### Code

```typescript
interface RAGResult {
  query: string;
  answer: string;
  sourceDocuments: Document[];
  validationDecision: string;
  riskScore: number;
  confidence: number;
}

async function queryRAGWithValidation(
  query: string,
  ragChain: RetrievalQA
): Promise<RAGResult> {
  // Step 1: Generate answer from RAG
  const ragResult = await ragChain.call({
    query: query
  });

  const answer = ragResult.text;
  const sourceDocuments: Document[] = ragResult.source_documents || [];

  // Step 2: Combine source documents into context
  const context = sourceDocuments
    .map(doc => doc.pageContent)
    .join('\n\n---\n\n');

  // Step 3: Validate against sources
  console.log('🔍 Validating RAG output...');
  const decision = await client.validate({
    prompt: query,
    output: answer,
    context: context,
    policy: 'rag_strict',  // Strict for RAG systems
    domain: 'rag',
    use_refinement: true
  });

  // Step 4: Return with validation metadata
  return {
    query,
    answer: decision.decision === 'allow' ? answer : 'Unable to provide a reliable answer.',
    sourceDocuments,
    validationDecision: decision.decision,
    riskScore: decision.risk_score,
    confidence: decision.confidence
  };
}

// Usage
const query = 'What are the benefits of machine learning?';
const result = await queryRAGWithValidation(query, myRagChain);

console.log(`Query: ${result.query}`);
console.log(`Decision: ${result.validationDecision}`);
console.log(`Risk: ${result.riskScore.toFixed(2)}`);
console.log(`Answer: ${result.answer}`);
```

### Advanced: Multi-Step RAG Validation

```typescript
async function queryRAGWithMultiStepValidation(
  query: string,
  ragChain: RetrievalQA
): Promise<{ answer: string; validationDetails: any }> {
  const ragResult = await ragChain.call({ query });
  const answer = ragResult.text;
  const sources = ragResult.source_documents || [];

  const context = sources.map(d => d.pageContent).join('\n\n');

  // Validate 3 different aspects
  const decisions = await Promise.all([
    // Validate against sources
    client.validate({
      prompt: query,
      output: answer,
      context: context,
      policy: 'rag_strict'
    }),
    // Validate for hallucinations (no context)
    client.validate({
      prompt: query,
      output: answer,
      policy: 'default'
    }),
    // Validate with domain-specific policy
    client.validate({
      prompt: query,
      output: answer,
      context: context,
      domain: 'rag',
      policy: 'rag_strict'
    })
  ]);

  const sourceMatch = decisions[0];
  const hallucination = decisions[1];
  const domainCheck = decisions[2];

  // Aggregate decisions
  const allSafe = decisions.every(d => d.decision === 'allow');
  const avgRisk = decisions.reduce((sum, d) => sum + d.risk_score, 0) / decisions.length;

  return {
    answer: allSafe ? answer : 'Unable to verify answer',
    validationDetails: {
      sourceMatch: sourceMatch.decision,
      hallucination: hallucination.decision,
      domainCheck: domainCheck.decision,
      averageRisk: avgRisk,
      detailedResults: decisions
    }
  };
}
```

---

## Example 4: Custom Retry Logic and Timeouts

Implement sophisticated retry strategies for different scenarios.

### Code

```typescript
interface RetryStrategy {
  maxAttempts: number;
  initialDelayMs: number;
  backoffMultiplier: number;
  maxDelayMs: number;
  jitterFactor: number;
}

const strategies = {
  aggressive: {
    maxAttempts: 5,
    initialDelayMs: 50,
    backoffMultiplier: 2,
    maxDelayMs: 5000,
    jitterFactor: 0.2
  } as RetryStrategy,

  conservative: {
    maxAttempts: 3,
    initialDelayMs: 200,
    backoffMultiplier: 1.5,
    maxDelayMs: 10000,
    jitterFactor: 0.1
  } as RetryStrategy,

  realtime: {
    maxAttempts: 1,
    initialDelayMs: 0,
    backoffMultiplier: 1,
    maxDelayMs: 0,
    jitterFactor: 0
  } as RetryStrategy
};

// Create client with custom retry strategy
function createClientWithStrategy(strategy: RetryStrategy) {
  return new GuardlyClient({
    apiKey: process.env.GUARDLY_API_KEY,
    baseUrl: 'http://localhost:5000',
    timeout: 60000,
    retryConfig: strategy
  });
}

// Usage examples
async function validateWithStrategy(
  input: any,
  strategy: 'aggressive' | 'conservative' | 'realtime'
) {
  const client = createClientWithStrategy(strategies[strategy]);

  console.log(`Using ${strategy} strategy...`);
  const startTime = Date.now();

  try {
    const decision = await client.validate(input);
    const duration = Date.now() - startTime;
    console.log(`✓ Success in ${duration}ms`);
    return decision;
  } catch (error) {
    const duration = Date.now() - startTime;
    console.log(`✗ Failed after ${duration}ms: ${error.message}`);
    throw error;
  }
}

// Practical example: Timeout-aware validation
async function validateWithAdaptiveTimeout(
  input: any,
  maxTotalTimeMs: number
): Promise<any> {
  const startTime = Date.now();
  let attempt = 1;
  const maxAttempts = 3;

  while (attempt <= maxAttempts) {
    const elapsedMs = Date.now() - startTime;
    const remainingMs = maxTotalTimeMs - elapsedMs;

    if (remainingMs < 1000) {
      console.log('⏱ Time budget exhausted, aborting');
      throw new Error('Timeout exceeded');
    }

    try {
      console.log(`Attempt ${attempt}/${maxAttempts} (${remainingMs}ms remaining)`);

      const client = new GuardlyClient({
        apiKey: 'key',
        baseUrl: 'http://localhost:5000',
        timeout: Math.min(remainingMs - 100, 30000)  // Leave 100ms buffer
      });

      const decision = await client.validate(input);
      return decision;

    } catch (error) {
      const elapsedMs = Date.now() - startTime;
      if (elapsedMs > maxTotalTimeMs) {
        throw new Error(`Exceeded total time budget (${elapsedMs}ms > ${maxTotalTimeMs}ms)`);
      }

      if (attempt < maxAttempts) {
        const delayMs = Math.min(100 * Math.pow(2, attempt - 1), 5000);
        console.log(`Retrying in ${delayMs}ms...`);
        await new Promise(resolve => setTimeout(resolve, delayMs));
      }
      attempt++;
    }
  }

  throw new Error('All retry attempts exhausted');
}

// Usage
try {
  const result = await validateWithAdaptiveTimeout(
    { prompt: '...', output: '...' },
    30000  // 30 second total budget
  );
} catch (error) {
  console.error('Validation failed:', error.message);
}
```

---

## Example 5: Error Handling and Recovery

Comprehensive error handling with fallback strategies.

### Code

```typescript
import {
  GuardlyApiError,
  GuardlyNetworkError,
  GuardlyValidationError
} from 'guardly-node-sdk';

enum FallbackStrategy {
  ALLOW = 'allow',           // Return output even if validation fails
  BLOCK = 'block',           // Block output if validation fails
  ABSTAIN = 'abstain',       // Return abstain decision
  REGENERATE = 'regenerate'  // Request regeneration
}

async function validateWithFallback(
  input: any,
  fallbackStrategy: FallbackStrategy
) {
  const client = new GuardlyClient({
    apiKey: 'key',
    baseUrl: 'http://localhost:5000',
    gracefulErrorHandling: fallbackStrategy === FallbackStrategy.ABSTAIN
  });

  try {
    return await client.validate(input);

  } catch (error) {
    if (error instanceof GuardlyValidationError) {
      console.error(`❌ Input validation error: ${error.message}`);
      console.error(`   Field: ${error.field}`);
      throw error;  // Always fail fast on input errors

    } else if (error instanceof GuardlyNetworkError) {
      console.error(`🌐 Network error: ${error.message}`);

      // Log for monitoring
      await logError('network_error', {
        message: error.message,
        timestamp: new Date()
      });

      // Apply fallback strategy
      switch (fallbackStrategy) {
        case FallbackStrategy.ALLOW:
          console.log('→ Fallback: Allowing output');
          return { decision: 'allow', confidence: 0, evidence: 'Network error, fallback allowed' };

        case FallbackStrategy.BLOCK:
          console.log('→ Fallback: Blocking output');
          return { decision: 'block', confidence: 1, evidence: 'Network error, fallback blocked' };

        case FallbackStrategy.ABSTAIN:
          console.log('→ Fallback: Abstaining');
          return { decision: 'abstain', confidence: 0, evidence: 'Network error, no validation' };

        case FallbackStrategy.REGENERATE:
          console.log('→ Fallback: Request regeneration');
          return { decision: 'regenerate', confidence: 0, evidence: 'Network error, try again' };
      }

    } else if (error instanceof GuardlyApiError) {
      console.error(`⚠️ API error ${error.statusCode}: ${error.message}`);

      if (error.statusCode === 429) {
        console.log('Rate limited, backing off...');
        await new Promise(resolve => setTimeout(resolve, 5000));
        // Retry (not shown for brevity)
      }

      throw error;

    } else {
      console.error('Unknown error:', error);
      throw error;
    }
  }
}

// Production middleware
async function validateWithMetrics(input: any) {
  const startTime = Date.now();
  let success = false;
  let errorType: string | null = null;

  try {
    const decision = await validateWithFallback(input, FallbackStrategy.ABSTAIN);
    success = true;
    return decision;

  } catch (error) {
    errorType = error.constructor.name;
    throw error;

  } finally {
    const duration = Date.now() - startTime;

    // Record metrics
    await recordMetric({
      operation: 'validate',
      duration_ms: duration,
      success,
      error_type: errorType,
      timestamp: new Date()
    });
  }
}
```

### Usage in Express Middleware

```typescript
app.post('/api/generate', async (req, res) => {
  try {
    const { prompt, model } = req.body;

    // Generate response
    const output = await generateWithGemini(prompt, model);

    // Validate with fallback
    const validation = await validateWithFallback(
      { prompt, output },
      FallbackStrategy.ABSTAIN
    );

    // Return response with validation metadata
    res.json({
      output,
      validation: {
        decision: validation.decision,
        risk_score: validation.risk_score,
        confidence: validation.confidence
      }
    });

  } catch (error) {
    if (error instanceof GuardlyValidationError) {
      res.status(400).json({ error: error.message });
    } else {
      res.status(500).json({ error: 'Internal server error' });
    }
  }
});
```

---

## Example 6: Monitoring, Logging, and Observability

Track validation metrics and integrate with observability platforms.

### Code

```typescript
import pino from 'pino';

// Structured logging
const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  transport: {
    target: 'pino-pretty',
    options: {
      colorize: true,
      translateTime: 'SYS:standard',
      ignore: 'pid,hostname'
    }
  }
});

// Metrics collection
class GuardlyMetricsCollector {
  private metrics = {
    totalValidations: 0,
    successfulValidations: 0,
    blockedOutputs: 0,
    errorCount: 0,
    totalLatencyMs: 0,
    latencies: [] as number[]
  };

  recordValidation(decision: any, latencyMs: number, error?: Error) {
    this.metrics.totalValidations++;
    this.metrics.totalLatencyMs += latencyMs;
    this.metrics.latencies.push(latencyMs);

    if (error) {
      this.metrics.errorCount++;
    } else {
      this.metrics.successfulValidations++;
      if (decision.decision === 'block') {
        this.metrics.blockedOutputs++;
      }
    }

    // Keep last 1000 latencies for p95 calculation
    if (this.metrics.latencies.length > 1000) {
      this.metrics.latencies.shift();
    }
  }

  getMetrics() {
    const sorted = [...this.metrics.latencies].sort((a, b) => a - b);
    const p50Index = Math.floor(sorted.length * 0.5);
    const p95Index = Math.floor(sorted.length * 0.95);
    const p99Index = Math.floor(sorted.length * 0.99);

    return {
      total_validations: this.metrics.totalValidations,
      success_rate: this.metrics.totalValidations > 0
        ? (this.metrics.successfulValidations / this.metrics.totalValidations * 100).toFixed(1) + '%'
        : 'N/A',
      blocked_count: this.metrics.blockedOutputs,
      error_count: this.metrics.errorCount,
      avg_latency_ms: (this.metrics.totalLatencyMs / Math.max(1, this.metrics.totalValidations)).toFixed(1),
      p50_latency_ms: sorted[p50Index]?.toFixed(1) || 'N/A',
      p95_latency_ms: sorted[p95Index]?.toFixed(1) || 'N/A',
      p99_latency_ms: sorted[p99Index]?.toFixed(1) || 'N/A'
    };
  }
}

const metricsCollector = new GuardlyMetricsCollector();

// Wrapper function with logging and metrics
async function validateAndLog(input: any): Promise<any> {
  const startTime = Date.now();
  const client = new GuardlyClient({ apiKey: 'key', baseUrl: 'http://localhost:5000' });

  try {
    logger.info({
      msg: 'Starting validation',
      prompt_length: input.prompt.length,
      output_length: input.output.length,
      policy: input.policy || 'default'
    });

    const decision = await client.validate(input);
    const latencyMs = Date.now() - startTime;

    metricsCollector.recordValidation(decision, latencyMs);

    logger.info({
      msg: 'Validation complete',
      decision: decision.decision,
      risk_score: decision.risk_score.toFixed(2),
      confidence: decision.confidence.toFixed(2),
      latency_ms: latencyMs
    });

    return decision;

  } catch (error) {
    const latencyMs = Date.now() - startTime;
    metricsCollector.recordValidation(null, latencyMs, error as Error);

    logger.error({
      msg: 'Validation failed',
      error: (error as Error).message,
      error_type: (error as Error).constructor.name,
      latency_ms: latencyMs
    });

    throw error;
  }
}

// Periodic metrics reporting
setInterval(() => {
  const metrics = metricsCollector.getMetrics();
  logger.info({
    msg: 'Metrics snapshot',
    ...metrics
  });
}, 60000);  // Every minute

// Express route with observability
app.get('/metrics', (req, res) => {
  res.json({
    timestamp: new Date(),
    metrics: metricsCollector.getMetrics()
  });
});

// Usage
async function handleGenerateRequest(req: any, res: any) {
  try {
    const { prompt } = req.body;

    logger.info({ msg: 'New generation request', prompt_preview: prompt.substring(0, 50) });

    // Generate
    const output = await generateResponse(prompt);

    // Validate
    const decision = await validateAndLog({
      prompt,
      output,
      policy: 'default'
    });

    // Return
    res.json({
      output: decision.decision === 'allow' ? output : null,
      safe: decision.decision === 'allow',
      metadata: {
        risk_score: decision.risk_score,
        confidence: decision.confidence,
        evidence: decision.evidence
      }
    });

  } catch (error) {
    logger.error({ msg: 'Request failed', error: (error as Error).message });
    res.status(500).json({ error: 'Internal server error' });
  }
}
```

### Integration with Observability Platforms

#### With OpenTelemetry

```typescript
import { trace, context } from '@opentelemetry/api';

const tracer = trace.getTracer('hallucination-guard');

async function validateWithTracing(input: any) {
  const span = tracer.startSpan('validation');

  return context.with(trace.setSpan(context.active(), span), async () => {
    try {
      const startTime = Date.now();
      const decision = await client.validate(input);
      const duration = Date.now() - startTime;

      span.setAttributes({
        'validation.decision': decision.decision,
        'validation.risk_score': decision.risk_score,
        'validation.latency_ms': duration
      });

      return decision;

    } catch (error) {
      span.recordException(error as Error);
      throw error;

    } finally {
      span.end();
    }
  });
}
```

#### With Langfuse (for trace export)

```bash
# Set environment variables
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...

# Traces are automatically exported to Langfuse
```

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

// Automatic trace export when LANGFUSE_* env vars are set
const client = new GuardlyClient({
  apiKey: 'key',
  baseUrl: 'http://localhost:5000'
  // Traces are exported automatically
});

// View traces at https://cloud.langfuse.com
```

---

## Summary

These examples demonstrate:

1. ✅ **Real-time validation** (Example 1) - Validate chatbot responses in production
2. ✅ **Batch processing** (Example 2) - Efficiently validate 100+ documents
3. ✅ **RAG integration** (Example 3) - Validate RAG system outputs
4. ✅ **Retry strategies** (Example 4) - Sophisticated error recovery
5. ✅ **Error handling** (Example 5) - Production-grade error handling
6. ✅ **Observability** (Example 6) - Monitoring and tracing

For more details, see:
- [SDK_INTEGRATION_GUIDE.md](./SDK_INTEGRATION_GUIDE.md)
- [API_REFERENCE.md](./API_REFERENCE.md)
- [guardly-node-sdk/USAGE.md](./guardly-node-sdk/USAGE.md)
