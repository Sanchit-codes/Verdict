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

## Quick Start

### Installation

```bash
# Install with all extras (recommended for development)
pip install -e ".[gemini,langchain,observability,dev]"

# Minimal runtime installation
pip install hallucination-guard
```

### Environment Variables

Copy `.env.example` to `.env` and configure your environment:

```bash
cp .env.example .env
# Edit .env with your actual values
```

**Required for integrations:**
- `GOOGLE_API_KEY`: Google AI API key for Gemini integration
- `LANGFUSE_PUBLIC_KEY` & `LANGFUSE_SECRET_KEY`: For trace export to Langfuse

**Optional SDK settings:**
- `HG_DEFAULT_POLICY`: Default policy (default, rag_strict, chatbot, no_prompt_check)
- `HG_DISABLE_HHEM`: Set to `true` for fast mode (heuristics + embeddings only)
- `HG_LOG_LEVEL`: Logging verbosity (WARNING, INFO, DEBUG)

**Development:**
- `FLASK_DEBUG`: Enable Flask debug mode for frontend development

See `.env.example` for complete configuration options.

### Basic Usage

```python
from hallucination_guard import Guard

# Initialize guard with a policy
guard = Guard(policy="safe")  # Use "safe" for fast/reliable, "development" for ML model testing

# Validate output
decision = guard.validate(
    prompt="What is the capital of France?",
    output="The capital of France is Paris.",
    context="France is a country in Europe. Its capital city is Paris.",
)

# Check decision
if decision.decision == "allow":
    print(f"✓ Safe to return (risk={decision.risk_score:.2f})")
elif decision.decision == "block":
    print(f"✗ Blocked (risk={decision.risk_score:.2f})")
```

### Testing Frontend

For development and testing, use the included web frontend:

```bash
# Install with frontend dependencies
pip install -e ".[dev]"

# Run the testing frontend
cd frontend && python run.py

# Or directly:
python frontend/run.py
```

The frontend provides:
- **Interactive prompt testing** with real-time validation
- **Tier 0.5 visualization** showing prompt security analysis
- **Policy comparison** across different configurations
- **Example scenarios** for testing various attack vectors
- **Detailed results** including risk scores, evidence, and latency

Access at: `http://localhost:5000`

### With Gemini Integration

```python
from hallucination_guard.integrations import GuardedGemini
import google.generativeai as genai

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
base_model = genai.GenerativeModel("gemini-2.0-flash")

# Wrap with guard (auto-retry on hallucinations)
guarded = GuardedGemini(
    model=base_model,
    policy="rag_strict",
    max_retries=2
)

# Generate with automatic validation
response = guarded.generate(
    prompt="Summarize this research paper.",
    context=paper_text
)
```

## Architecture

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
pytest --cov=hallucination_guard --cov-report=html

# Fast mode (skip model downloads)
HG_DISABLE_HHEM=true pytest tests/test_heuristics.py

# Development mode (relaxed timeouts for model testing)
pytest tests/ -k "not slow"  # Use development policy in tests
```

### Code Quality

```bash
# Format
black hallucination_guard/ tests/ examples/

# Lint
ruff check hallucination_guard/ tests/ examples/

# Type check
mypy hallucination_guard/ --strict
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
