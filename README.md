# HallucinationGuard SDK

**Vendor-neutral Python SDK for preventing AI hallucinations through inline validation—without LLM-as-a-judge calls.**

## Overview

HallucinationGuard validates AI-generated text using a fast, deterministic three-tier cascade (heuristics → embeddings → classifier models) before it reaches users. No mandatory server infrastructure. Pure Python library optimized for production.

### Core Features

- **3-Tier Validation Cascade**: Fast heuristics (<5ms) → embedding similarity (<30ms) → HHEM classifier (<80ms)
- **Zero Server Dependencies**: Pure Python library, no databases or control planes required
- **CPU-Optimized**: Target p95 latency < 100ms on CPU-only deployments
- **Graceful Degradation**: One broken validator never crashes the pipeline
- **Vendor-Neutral**: Works with any LLM (Gemini, OpenAI, local models, etc.)
- **Policy-Driven**: YAML-based policies for domain-specific tuning (RAG, chatbots, creative writing)
- **ArmorIQ Integration**: Optional pre-execution intent enforcement layer

## 🚀 Quick Start (5 Minutes)

### For JavaScript/TypeScript Developers

```bash
# 1. Install Node SDK
npm install guardly-node-sdk

# 2. Start Flask API server (in another terminal)
python server/run.py

# 3. Validate your first output
import { GuardlyClient } from 'guardly-node-sdk';

const client = new GuardlyClient({ 
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000' 
});

const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Europe. Its capital is Paris.'
});

if (decision.decision === 'allow') {
  console.log('✓ Output is safe');
} else if (decision.decision === 'block') {
  console.log('✗ Hallucination detected');
}
```

### For Python Developers

```python
from verdict import Guard

# Initialize guard with a policy
guard = Guard(policy="default")

# Validate output
decision = guard.validate(
    prompt="What is the capital of France?",
    output="The capital of France is Paris.",
    context="France is a country in Europe. Its capital is Paris.",
)

# Check decision
if decision.decision == "allow":
    print(f"✓ Safe to return (risk={decision.risk_score:.2f})")
elif decision.decision == "block":
    print(f"✗ Blocked (risk={decision.risk_score:.2f})")
```

### Full Getting Started Guide

**→ [QUICKSTART.md](QUICKSTART.md)** — Complete 5-minute setup guide with:
- Step-by-step installation for all package managers
- Server startup and configuration
- First validation in 3 different languages
- Common patterns and troubleshooting

### Installation

```bash
# Node.js SDK
npm install guardly-node-sdk

# Python SDK (with all extras)
pip install -e ".[gemini,langchain,observability,dev]"
```

## Documentation

Comprehensive guides for deploying and using HallucinationGuard across the full stack:

### Getting Started

- **[QUICKSTART.md](./QUICKSTART.md)** — First-time user guide (5 minutes)
  - Step-by-step npm/pip installation
  - Your first validation in 3 languages (TypeScript, JavaScript, Python)
  - Common patterns and health checks
  - Troubleshooting tips

### Gemini Generation + Validation

- **[GEMINI_SETUP.md](./GEMINI_SETUP.md)** — Gemini integration guide (5 minutes)
  - Get a free Google API key (15 req/min free tier)
  - Install with Gemini support: `pip install verdict[gemini]`
  - Generate text with Gemini 2.5 Flash, validate with HallucinationGuard 3-tier cascade
  - Complete code example showing faithful vs. hallucinated outputs
  - Troubleshooting (API quota, latency, model downloads)

- **[gemini_validation_demo.py](./examples/gemini_validation_demo.py)** — Standalone demo script
  - Shows full generate → validate → decide flow
  - 3 demo cases: faithful output, hallucination detection, ambiguous flagging
  - Policy configuration display with validator details
  - Rich terminal output with decision colors and evidence

### Integration & Deployment

- **[SDK_INTEGRATION_GUIDE.md](./SDK_INTEGRATION_GUIDE.md)** — Complete stack integration (789 lines)
  - Full architecture overview with data flow
  - Node.js client configuration (all options documented)
  - Flask server setup and environment variables
  - Policy selection (default, rag_strict, chatbot)
  - Batch validation (parallel vs. sequential)
  - Deployment guides (Gunicorn, Docker, Kubernetes)
  - Performance tuning table

- **[API_REFERENCE.md](./API_REFERENCE.md)** — REST API specification (757 lines)
  - All 4 endpoints: `/api/validate`, `/api/batch_validate`, `/api/health`, `/api/version`
  - Complete request/response schemas with examples
  - Error codes and decision types
  - Built-in policy specifications
  - Rate limiting and timeout specs
  - curl, TypeScript, and Python examples for all endpoints

### SDKs & Examples

- **[guardly-node-sdk/USAGE.md](./guardly-node-sdk/USAGE.md)** — Node.js SDK reference (889 lines)
  - Installation (npm, yarn, pnpm)
  - Configuration with all options
  - Single validation (basic, with context, with policy, with domain, with refinement)
  - Batch validation (parallel and sequential)
  - Retry configuration (strategies: aggressive, conservative, realtime)
  - Error handling (GuardlyError, GuardlyNetworkError, GuardlyApiError, GuardlyValidationError)
  - Type reference (ValidationInput, ValidationDecision, TierResult, BatchValidationResult)
  - Best practices and production patterns

- **[EXAMPLES.md](./EXAMPLES.md)** — Real-world integration examples (935 lines)
  - Example 1: Simple chat message validation
  - Example 2: Batch processing documents with error recovery
  - Example 3: RAG system integration with LangChain
  - Example 4: Custom retry logic and adaptive timeouts
  - Example 5: Error handling and recovery strategies
  - Example 6: Monitoring, logging, and observability (OpenTelemetry, Langfuse)

---

## Full Stack Architecture

HallucinationGuard consists of three integrated layers working together to prevent AI hallucinations:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Client Applications                            │
│  (Web, Mobile, Backend, ChatBot, RAG System, LLM Agent)         │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP REST
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│         Layer 2: Flask REST API Server (Python)                 │
│  Wraps SDK, provides 4 HTTP endpoints with authentication       │
│                                                                   │
│  ╔─────────────────────────────────────────────────────────┐   │
│  ║  POST /api/validate              Single validation      ║   │
│  ║  POST /api/batch_validate        Parallel/sequential    ║   │
│  ║  GET /api/health                 Health + models status ║   │
│  ║  GET /api/version                Version information    ║   │
│  ╚─────────────────────────────────────────────────────────┘   │
└────────────┬─────────────────────────────────────────────────────┘
             │ Direct Python API
             ↓
┌─────────────────────────────────────────────────────────────────┐
│      Layer 1: HallucinationGuard Python SDK (Core)               │
│  Pure Python validation engine - no external dependencies       │
│                                                                   │
│  ╔──────────────────────────────────────────────────────────┐  │
│  ║ Tier 1: Heuristics (<5ms)                                ║  │
│  ║ ├─ context_coverage_ratio                                ║  │
│  ║ ├─ entity_overlap_check                                  ║  │
│  ║ └─ length_anomaly_check                                  ║  │
│  ║                                                            ║  │
│  ║ Tier 2: Embedding Similarity (<30ms)                     ║  │
│  ║ └─ all-MiniLM-L6-v2 cosine similarity                    ║  │
│  ║                                                            ║  │
│  ║ Tier 3: HHEM Classifier (<80ms)                          ║  │
│  ║ └─ vectara/hallucination_evaluation_model                ║  │
│  ║                                                            ║  │
│  ║ Decision Engine: Weighted aggregation → decision         ║  │
│  ╚──────────────────────────────────────────────────────────┘  │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────────┐
│            Layer 3: Node.js/TypeScript SDK Client                │
│  Lightweight wrapper around Flask API with typed interfaces     │
│                                                                   │
│  ╔──────────────────────────────────────────────────────────┐  │
│  ║ GuardlyClient                                             ║  │
│  ║ ├─ validate()        → Single validation                 ║  │
│  ║ ├─ batchValidate()   → Parallel/sequential batch         ║  │
│  ║ ├─ getHealth()       → Health check                      ║  │
│  ║ └─ getVersion()      → Version info                      ║  │
│  ║                                                            ║  │
│  ║ Features:                                                  ║  │
│  ║ • Exponential backoff retry logic                         ║  │
│  ║ • Comprehensive error handling                            ║  │
│  ║ • Full TypeScript support with types                      ║  │
│  ║ • Graceful degradation (optional abstain on error)        ║  │
│  ╚──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Layer Breakdown

| Layer | Component | Tech | Purpose | Latency |
|-------|-----------|------|---------|---------|
| **1** | HallucinationGuard SDK | Python 3.10+ | Core validation engine | p95 < 100ms |
| **2** | Flask REST API | Python + Flask | HTTP API wrapper + middleware | +10-20ms |
| **3** | guardly-node-sdk | TypeScript/Node.js | Client library + retry logic | +network latency |

### Communication Flow

1. **Client** (web/mobile/backend) sends validation request via HTTP to Layer 2
2. **Flask API Server** (Layer 2) validates request, calls Layer 1 SDK
3. **HallucinationGuard SDK** (Layer 1) runs 3-tier cascade:
   - Tier 1 (fast) → if clear, return decision
   - Tier 2 (medium) → if unclear, run embedding similarity
   - Tier 3 (slow) → if still unclear, run HHEM classifier
4. **Decision Engine** aggregates scores, returns decision (allow/block/regenerate/abstain)
5. **Flask API** returns structured JSON response to client
6. **Node.js SDK** (Layer 3) receives response, handles retries and errors

### Key Properties

- **Zero mandatory server infrastructure**: Layer 1 is pure Python, works offline
- **Graceful degradation**: Any layer can fail without crashing the pipeline
- **CPU-optimized**: All models run on CPU (no GPU required)
- **Policy-driven**: All validation rules configurable via YAML
- **Vendor-neutral**: Works with any LLM (Gemini, OpenAI, local models, etc.)

---

## Validation Architecture

```
User Prompt
    ↓
[Tier 0.5: Prompt Security] (<15ms)
    ├─ Intent Detection (question, instruction, creative, etc.)
    ├─ Injection Detection (jailbreak, context-switching, role injection)
    ├─ PII Detection (emails, SSNs, credit cards)
    ├─ Sensitivity Tagging (medical, financial, legal domains)
    └─ Entity Extraction (key entities and topics)
    ↓
LLM Generation (e.g., Gemini 2.0)
    ↓
HallucinationGuard SDK (3-tier cascade):
    Tier 1: Heuristics (<5ms)
      ├─ context_coverage_ratio
      ├─ entity_overlap_check
      └─ length_anomaly_check
    Tier 2: Embedding Similarity (<30ms)
      └─ cosine(context_embed, output_embed)
    Tier 3: HHEM Classifier (<80ms)
      └─ vectara/hallucination_evaluation_model
    Decision Engine:
      └─ weighted_avg → allow/block/regenerate/abstain
    ↓
Output (if allowed)
```

## Automatic Prompt Analysis (Tier 0.5)

HallucinationGuard automatically analyzes every input prompt before validating LLM output:

- **Intent Detection**: Classifies prompts as question, instruction, creative, statement, chat, or system command
- **Security Checks**: Detects prompt injection attempts, jailbreaks, context switching, and role injection attacks
- **Sensitivity Tagging**: Flags prompts touching sensitive domains (medical, financial, legal, personal, proprietary)
- **PII Detection**: Identifies and flags personally identifiable information (emails, SSNs, credit cards, phone numbers)
- **Entity Extraction**: Pulls key named entities, topics, and contexts from prompts

All structured metadata from Tier 0.5 is included in the decision result for downstream handling and routing decisions. For high-sensitivity domains, you can tighten validation thresholds automatically.

Learn more: [Structured Prompt Processing](docs/PROMPT_STRUCTURE.md)

## Pre-Configured Policies

- **`default.yaml`**: Balanced general-purpose policy
- **`rag_strict.yaml`**: High-risk domains (healthcare, finance)—lower threshold, regenerate on failure
- **`chatbot.yaml`**: Low-latency chatbots—heuristics + embeddings only
- **`safe.yaml`**: Fast and reliable—prompt security + heuristics only (<1ms latency)
- **`development.yaml`**: Relaxed timeouts for testing with ML models

Custom policies can be created via YAML configuration.

### Development Policy

For development and testing with relaxed timeouts (to accommodate first-time model loading):

```bash
guard = Guard(policy="development")
```

The `development.yaml` policy includes:
- **30 second latency budget** (vs 150ms in production policies)
- **Relaxed validator timeouts**: 10s for embedding, 15s for HHEM
- **Same validation logic** but more tolerant of model loading delays

**Note**: HHEM validator may still fail due to tokenizer compatibility issues with some environments. Use `HG_DISABLE_HHEM=true` for pure heuristics + embeddings validation.

## Development

### Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with dev dependencies
pip install -e ".[gemini,langchain,observability,dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=verdict --cov-report=html

# Fast mode (skip model downloads)
HG_DISABLE_HHEM=true pytest tests/test_heuristics.py

# Development mode (relaxed timeouts for model testing)
pytest tests/ -k "not slow"  # Use development policy in tests
```

### Code Quality

```bash
# Format
black verdict/ tests/ examples/

# Lint
ruff check verdict/ tests/ examples/

# Type check
mypy verdict/ --strict
```

## Technology Stack

**Core Runtime:**
- Python ≥3.10
- pydantic ^2.7 (schema validation)
- pyyaml ^6.0 (policy parsing)
- sentence-transformers ^3.1 (embedding similarity)
- torch ^2.3 CPU (backend)
- transformers ^4.44 (HHEM model)
- numpy ^1.26 (score aggregation)

**Optional Integrations:**
- google-generativeai (Gemini integration)
- langchain-core (RAG chains)
- langfuse (observability & tracing)

**Models (auto-downloaded):**
- HHEM 2.1-Open (~400MB): Tier 3 faithfulness classifier
- all-MiniLM-L6-v2 (~80MB): Tier 2 embedding model

## Design Principles

1. **No LLM-as-a-judge** in the runtime validation pipeline
2. **Zero mandatory server infrastructure** (pure Python library)
3. **Graceful degradation always**—never crash the pipeline
4. **Target latency**: p95 < 100ms across all tiers, CPU-only

## License

MIT

## Contributing

Contributions welcome! Please ensure:
- All tests pass (`pytest`)
- Code is formatted (`black`) and linted (`ruff`)
- Type checking passes (`mypy --strict`)
- New features include unit tests (min 80% coverage)

## Roadmap

- [x] Project structure and dependency setup
- [ ] Core validation engine (Guard, Pipeline, Decision)
- [x] Tier 1: Heuristics validator
- [x] Tier 2: Embedding validator
- [x] Tier 3: HHEM validator
- [x] Policy system (YAML loader, schema)
- [x] Gemini integration (GuardedGemini)
- [x] ArmorIQ integration (intent enforcement)
- [x] LangChain integration
- [ ] CLI tools (eval, benchmark)
- [ ] HaluBench evaluation
- [ ] Phase 2: Lynx 8B validator (GPU)

---

**Status**: Early Development (v0.1.0)  
**Target**: Production-ready SDK for preventing AI hallucinations

---

## REST API & Deployment

### REST API Documentation

Complete API reference with all endpoints, request/response examples, and curl recipes:

**[→ REST API Documentation](docs/REST_API.md)**

Key endpoints:
- `POST /validate` - Single text validation
- `POST /validate/batch` - Batch validation (parallel/sequential)
- `GET /health` - Health check
- `GET /version` - Version information
- `GET /config/policies` - List available policies

### Deployment Guide

Production deployment guide covering:
- Environment variables
- Docker & Kubernetes setup
- Gunicorn + Nginx configuration
- Performance tuning
- Monitoring & logging
- Troubleshooting

**[→ Deployment Guide](docs/DEPLOYMENT.md)**

### Integration Tests

26 comprehensive end-to-end integration tests covering all endpoints, authentication, error handling, and graceful degradation:

```bash
pytest tests/test_integration_e2e.py -v
```

---

## Node.js/TypeScript SDK

### Installation

```bash
npm install guardly-ai
```

### Quick Start

```typescript
import { GuardlyClient } from 'guardly-ai';

const client = new GuardlyClient({
  apiKey: 'your-api-key',
  baseUrl: 'http://localhost:5000'
});

const decision = await client.validate({
  prompt: 'What is the capital of France?',
  output: 'The capital of France is Paris.',
  context: 'France is a country in Europe. Its capital is Paris.'
});

console.log(`Decision: ${decision.decision}`);
console.log(`Risk: ${decision.risk_score}`);
```

### SDK Documentation

Complete Node.js/TypeScript SDK guide with all methods, error handling, and examples:

**[→ Node SDK Usage Guide](docs/NODE_SDK_USAGE.md)**

Key methods:
- `validate()` - Single validation
- `validateBatch()` - Batch validation
- `healthCheck()` - Health status
- `getVersion()` - Version info
- `getPolicies()` - List policies

---

## Example Servers

### Flask API Server

Standalone Flask server with authentication and comprehensive validation endpoints:

```bash
export VERDICT_API_KEYS="key1,key2,key3"
python3 examples/flask_api_server.py
```

Access at: `http://localhost:5000`

**[→ Flask Server Code](examples/flask_api_server.py)**

### Node SDK Client

Complete TypeScript client example demonstrating all SDK methods:

```bash
export VERDICT_API_KEY="your-key"
npx tsx examples/node_sdk_client.ts
```

**[→ Node SDK Example](examples/node_sdk_client.ts)**

---

## Architecture

```
Prompt → LLM (Gemini) → Output
                    ↓
            HallucinationGuard (3-tier cascade)
            ├─ Tier 1: Heuristics (<5ms)
            ├─ Tier 2: Embedding (<30ms)
            └─ Tier 3: HHEM (<80ms)
                    ↓
            Decision (allow/block/regenerate/abstain)
                    ↓
            Flask REST API (optional)
                    ↓
            User/Application
```

---

## Project Structure

```
verdict/
├── verdict/       # Core Python SDK
│   ├── core/                  # Main guard, pipeline, decision engine
│   ├── validators/            # Tier 1-3 validators
│   ├── policy/                # Policy configuration
│   └── integrations/          # Gemini, LangChain, ArmorIQ
├── frontend/                  # Flask REST API
│   ├── app.py                 # Flask application
│   ├── routes/                # API endpoints
│   ├── schemas.py             # Request/response schemas
│   ├── service.py             # Guard service layer
│   └── middleware.py          # Authentication middleware
├── examples/
│   ├── flask_api_server.py    # Standalone Flask server
│   └── node_sdk_client.ts     # TypeScript example
├── docs/
│   ├── REST_API.md            # API reference
│   ├── DEPLOYMENT.md          # Deployment guide
│   └── NODE_SDK_USAGE.md      # SDK documentation
├── tests/
│   ├── test_integration_e2e.py  # Integration tests (26 tests)
│   └── test_routes.py           # Route unit tests
└── pyproject.toml             # Package configuration
```

---

## Performance

**Latency (p95):**
- Heuristics: < 5ms
- Embedding: < 30ms
- HHEM: < 80ms
- **Total: < 100ms**

**Cold Start:**
- First request: ~6-8 seconds (models cached after)
- Subsequent requests: < 100ms

**Throughput:**
- Single validation: ~10 req/sec per core
- Batch (parallel, 10 items): ~1 batch/sec

---

## Security

- ✅ Stateless design (no server dependencies)
- ✅ Bearer token authentication
- ✅ No model downloading required (auto-cached)
- ✅ Graceful degradation (no crashes)
- ✅ Pydantic schema validation (input sanitization)
- ✅ Comprehensive error handling

---

## Support

- **Issues:** [GitHub Issues](https://github.com/guardly/guardly-ai/issues)
- **REST API Docs:** [docs/REST_API.md](docs/REST_API.md)
- **Deployment Docs:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Node SDK Docs:** [docs/NODE_SDK_USAGE.md](docs/NODE_SDK_USAGE.md)

---

## License

MIT License - See LICENSE file for details
