# Guardly SDK Usage Examples

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Error Handling](#error-handling)
3. [Advanced Configuration](#advanced-configuration)
4. [Real-World Scenarios](#real-world-scenarios)

## Basic Usage

### Minimal Example

```typescript
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!
});

const decision = await client.validate({
  prompt: 'What is 2+2?',
  output: '2+2 equals 4',
});

console.log(decision.decision);    // 'allow' | 'block' | 'regenerate' | 'abstain'
console.log(decision.risk_score);  // 0-1
console.log(decision.evidence);    // Explanation
```

### With Context

```typescript
const decision = await client.validate({
  prompt: 'What is the tallest mountain?',
  output: 'Mount Everest is the tallest mountain at 8,849 meters.',
  context: 'Mount Everest is located in the Himalayas and is 8,849 meters tall.'
});

if (decision.decision === 'allow') {
  console.log('✓ Output is accurate');
}
```

### Handling All Decision Types

```typescript
const decision = await client.validate({ prompt, output, context });

switch (decision.decision) {
  case 'allow':
    console.log('✓ Safe to use (risk:', decision.risk_score, ')');
    return decision.output;
  
  case 'block':
    console.error('✗ Hallucination detected:', decision.evidence);
    throw new Error(decision.evidence);
  
  case 'regenerate':
    console.log('↻ Try regenerating with hint:', decision.suggested_fix);
    // Retry generation with suggested_fix as additional prompt
    break;
  
  case 'abstain':
    console.log('? Insufficient data (service unavailable or graceful error)');
    // Handle uncertainty gracefully
    break;
}
```

## Error Handling

### Input Validation Errors

```typescript
import { GuardlyValidationError } from 'guardly-node-sdk';

try {
  await client.validate({
    prompt: '',  // Error: required
    output: 'test'
  });
} catch (error) {
  if (error instanceof GuardlyValidationError) {
    console.log('Field:', error.field);       // 'prompt'
    console.log('Details:', error.details);   // 'prompt must be a non-empty string'
    console.log('Message:', error.message);   // Full error message
  }
}
```

### API Errors

```typescript
import { GuardlyApiError } from 'guardly-node-sdk';

try {
  await client.validate({ prompt: 'test', output: 'test' });
} catch (error) {
  if (error instanceof GuardlyApiError) {
    // Check error type
    if (error.isAuthError()) {
      console.error('Invalid API key');
      // Refresh credentials
    } else if (error.isClientError()) {
      console.error('Bad request:', error.code);
      // Fix input
    } else if (error.isServerError()) {
      console.error('Server error:', error.message);
      // Retry later
    }
    
    // Access error details
    console.log('Status:', error.statusCode);   // 401, 500, etc.
    console.log('Code:', error.code);           // 'INVALID_API_KEY', etc.
    console.log('Details:', error.details);     // Additional info
  }
}
```

### Network Errors

```typescript
import { GuardlyNetworkError } from 'guardly-node-sdk';

try {
  await client.validate({ prompt: 'test', output: 'test' });
} catch (error) {
  if (error instanceof GuardlyNetworkError) {
    console.error('Network error:', error.message);
    console.error('Original cause:', error.originalError);
    // Implement retry logic or fallback
  }
}
```

### Graceful Error Handling

Enable graceful error handling to avoid exceptions:

```typescript
const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!,
  gracefulErrorHandling: true  // Never throw, return abstain instead
});

// API is down, network error, or validation timeout → returns abstain decision
const decision = await client.validate({
  prompt: 'Test',
  output: 'Test output'
});

if (decision.decision === 'abstain') {
  // Service unavailable, proceed with caution or use fallback
  console.warn('Validation service unavailable, using abstain decision');
}
```

## Advanced Configuration

### Custom Base URL

```typescript
const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'https://api.example.com',  // Custom Guardly server
  timeout: 60000                       // 60 second timeout
});
```

### Custom Timeout

```typescript
const client = new GuardlyClient({
  apiKey: 'your-api-key',
  timeout: 5000  // 5 second timeout (default: 30s)
});

// Long-running validations might timeout, handle gracefully
try {
  const decision = await client.validate({...});
} catch (error) {
  if (error instanceof GuardlyNetworkError) {
    console.log('Validation timed out');
  }
}
```

### Custom User-Agent

```typescript
const client = new GuardlyClient({
  apiKey: 'your-api-key',
  userAgent: 'MyApp/1.0.0 (custom identification)'
});
```

## Real-World Scenarios

### Scenario 1: LLM Chat Application

```typescript
import { GuardlyClient, GuardlyApiError, GuardlyNetworkError } from 'guardly-node-sdk';

const client = new GuardlyClient({
  apiKey: process.env.GUARDLY_API_KEY!,
  gracefulErrorHandling: true  // Don't crash chat on validation error
});

async function processLLMResponse(
  userMessage: string,
  llmResponse: string,
  context?: string
): Promise<{ safe: boolean; response: string; reason?: string }> {
  const decision = await client.validate({
    prompt: userMessage,
    output: llmResponse,
    context,
    domain: 'chatbot'
  });

  switch (decision.decision) {
    case 'allow':
      return { safe: true, response: llmResponse };
    
    case 'block':
      return {
        safe: false,
        response: 'I cannot provide this information',
        reason: decision.evidence
      };
    
    case 'regenerate':
      // Log regeneration request for monitoring
      console.log('Regeneration needed:', decision.suggested_fix);
      return {
        safe: false,
        response: 'Let me reconsider that...',
        reason: 'Response needs refinement'
      };
    
    case 'abstain':
      // Assume safe if validation service is down
      console.warn('Validation service unavailable');
      return { safe: true, response: llmResponse };
  }
}

// Usage
const response = await processLLMResponse(
  'What is AI safety?',
  'AI safety is the field of...',
  'AI safety overview document...'
);

if (!response.safe) {
  console.log('❌', response.reason);
} else {
  console.log('✓', response.response);
}
```

### Scenario 2: Batch Validation

```typescript
async function validateBatch(
  prompt: string,
  outputs: string[],
  context: string
): Promise<{ output: string; decision: string; riskScore: number }[]> {
  const results = await Promise.allSettled(
    outputs.map(output =>
      client.validate({ prompt, output, context })
    )
  );

  return results.map((result, index) => {
    if (result.status === 'fulfilled') {
      const decision = result.value;
      return {
        output: outputs[index],
        decision: decision.decision,
        riskScore: decision.risk_score
      };
    } else {
      // Treat errors as abstain (uncertain)
      return {
        output: outputs[index],
        decision: 'abstain',
        riskScore: 0.5
      };
    }
  });
}

// Usage
const generations = [
  'Answer A...',
  'Answer B...',
  'Answer C...'
];

const validated = await validateBatch(
  'What is X?',
  generations,
  'Context about X...'
);

// Select best safe answer
const bestSafe = validated
  .filter(r => r.decision !== 'block')
  .sort((a, b) => a.riskScore - b.riskScore)[0];

console.log('Selected:', bestSafe.output);
```

### Scenario 3: Domain-Specific Validation

```typescript
// Medical domain with strict policy
const medicalClient = new GuardlyClient({ apiKey: 'key' });

const medicalDecision = await medicalClient.validate({
  prompt: 'Describe treatment for condition X',
  output: 'Treatment involves...',
  context: 'Medical literature...',
  policy: 'medical_strict',    // Stricter thresholds for healthcare
  domain: 'healthcare',
  use_refinement: true         // Get improvement suggestions
});

// Financial domain
const financialDecision = await medicalClient.validate({
  prompt: 'What is investment strategy X?',
  output: 'Strategy X involves...',
  context: 'Financial data...',
  policy: 'financial_strict',  // Stricter for financial advice
  domain: 'finance'
});
```

### Scenario 4: Monitoring & Metrics

```typescript
interface ValidationMetrics {
  totalValidations: number;
  blockedCount: number;
  regenerateCount: number;
  abstainCount: number;
  averageRiskScore: number;
  averageLatency: number;
}

class ValidationMonitor {
  private metrics: ValidationMetrics = {
    totalValidations: 0,
    blockedCount: 0,
    regenerateCount: 0,
    abstainCount: 0,
    averageRiskScore: 0,
    averageLatency: 0
  };

  async validate(input: ValidationInput): Promise<ValidationDecision> {
    const decision = await client.validate(input);
    this.updateMetrics(decision);
    return decision;
  }

  private updateMetrics(decision: ValidationDecision) {
    const m = this.metrics;
    
    m.totalValidations++;
    
    switch (decision.decision) {
      case 'block':
        m.blockedCount++;
        break;
      case 'regenerate':
        m.regenerateCount++;
        break;
      case 'abstain':
        m.abstainCount++;
        break;
    }
    
    // Update running average risk score
    const prevAvg = m.averageRiskScore;
    m.averageRiskScore = 
      (prevAvg * (m.totalValidations - 1) + decision.risk_score) / 
      m.totalValidations;
    
    // Update running average latency
    const latency = decision.latency_ms || 0;
    const prevLatency = m.averageLatency;
    m.averageLatency = 
      (prevLatency * (m.totalValidations - 1) + latency) / 
      m.totalValidations;
  }

  getMetrics(): ValidationMetrics {
    return { ...this.metrics };
  }

  reportMetrics() {
    const m = this.metrics;
    console.log('=== Validation Metrics ===');
    console.log(`Total: ${m.totalValidations}`);
    console.log(`Blocked: ${m.blockedCount} (${((m.blockedCount/m.totalValidations)*100).toFixed(1)}%)`);
    console.log(`Regenerate: ${m.regenerateCount}`);
    console.log(`Abstain: ${m.abstainCount}`);
    console.log(`Avg Risk: ${m.averageRiskScore.toFixed(3)}`);
    console.log(`Avg Latency: ${m.averageLatency.toFixed(0)}ms`);
  }
}

// Usage
const monitor = new ValidationMonitor();

for (const item of items) {
  const decision = await monitor.validate({
    prompt: item.prompt,
    output: item.generatedOutput
  });
  // ...
}

monitor.reportMetrics();
```

### Scenario 5: Retry with Backoff

```typescript
async function validateWithRetry(
  input: ValidationInput,
  maxRetries: number = 3,
  backoffMs: number = 1000
): Promise<ValidationDecision> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await client.validate(input);
    } catch (error) {
      if (
        error instanceof GuardlyNetworkError &&
        attempt < maxRetries - 1
      ) {
        // Retry on network error with exponential backoff
        const delay = backoffMs * Math.pow(2, attempt);
        console.log(`Retry ${attempt + 1}/${maxRetries} after ${delay}ms`);
        await new Promise(resolve => setTimeout(resolve, delay));
      } else {
        throw error;
      }
    }
  }
  
  // Unreachable
  throw new Error('Max retries exceeded');
}

// Usage
const decision = await validateWithRetry({
  prompt: 'test',
  output: 'test output'
}, 3, 500);
```

---

**More examples at**: https://github.com/Sanchit-codes/guardly-node-sdk/tree/main/examples
