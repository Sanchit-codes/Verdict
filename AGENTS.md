You are an experienced, pragmatic software engineering AI agent. Do not over-engineer a solution when a simple one is possible. Keep edits minimal. If you want an exception to ANY rule, you MUST stop and get permission first.

# HallucinationGuard SDK — Agent Instructions

## Project Overview

**HallucinationGuard** is a vendor-neutral Python SDK that prevents AI hallucinations in production through inline validation—without LLM-as-a-judge calls. The system validates generated text using a three-tier cascade (heuristics → embeddings → classifier models) before it reaches users.

**ArmorIQ integration** adds a second layer of protection by enforcing intent alignment on agent actions pre-execution, stopping bad actions from executing even when the text passes validation.

**Core Value Proposition:**
- **HallucinationGuard**: Stops bad text from reaching users (output validation)
- **ArmorIQ**: Stops bad actions from executing (behavior validation)
- Together they cover both ways AI breaks in production

**Key Design Principles:**
1. No LLM-as-a-judge calls in the runtime validation pipeline
2. Zero mandatory server infrastructure (pure Python library)
3. Graceful degradation always—never crash the pipeline
4. Target latency: p95 < 100ms across all tiers, CPU-only

### Technology Stack

**Core Runtime:**
- **Python**: >=3.10
- **pydantic**: ^2.7 (all schema validation—policies, results, traces, decisions)
- **pyyaml**: ^6.0 (policy YAML parsing)
- **sentence-transformers**: ^3.1 (embedding-based similarity, Tier 2)
- **torch**: ^2.3 CPU (backend for transformers and HHEM)
- **transformers**: ^4.44 (HHEM model loading from HuggingFace)
- **numpy**: ^1.26 (cosine similarity and score aggregation)

**Optional Integrations:**
- **google-generativeai**: `[gemini]` extra—primary hackathon model
- **langchain-core**: `[langchain]` extra—RAG chain integration
- **langfuse**: `[observability]` extra—trace export and dashboard

**Dev/Eval:**
- **pytest**: Unit testing
- **pytest-asyncio**: Async test support
- **datasets**: HaluBench and LibreEval benchmark datasets
- **typer**: CLI tool framework
- **rich**: Terminal output formatting
- **locust**: Load testing for latency verification

**Models (auto-downloaded on first use):**
- **HHEM 2.1-Open** (`vectara/hallucination_evaluation_model`): ~400MB, Tier 3 faithfulness classifier
- **all-MiniLM-L6-v2** (`sentence-transformers/all-MiniLM-L6-v2`): ~80MB, Tier 2 embedding similarity
- **Lynx 8B** (`PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct`): ~16GB, Phase 2 only (GPU required, skip for MVP)

---

## Reference

### Architecture Overview

```
User Prompt → Gemini 2.0 (generates text)
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
ArmorIQ Intent Enforcement (optional, pre-execution)
    └─ Does action belong to declared task?
    ↓
Tool/API Execution
```

### Directory Structure

```
hallucination-guard/
├── hallucination_guard/       # Main package
│   ├── core/                  # Core validation engine
│   │   ├── guard.py           # Main Guard class (public API)
│   │   ├── pipeline.py        # 3-tier cascade orchestrator
│   │   ├── decision.py        # Score aggregation & decision mapping
│   │   └── trace.py           # Langfuse-compatible trace logging
│   ├── validators/            # Validation tier implementations
│   │   ├── base.py            # BaseValidator interface + schemas
│   │   ├── heuristics.py      # Tier 1: Fast deterministic checks
│   │   ├── embedding.py       # Tier 2: Cosine similarity
│   │   ├── hhem.py            # Tier 3: HHEM faithfulness classifier
│   │   ├── lynx.py            # Phase 2: Lynx 8B (GPU, skip for MVP)
│   │   └── safety.py          # Optional: Llama Guard safety checks
│   ├── policy/                # Policy configuration system
│   │   ├── schema.py          # Pydantic models for policies
│   │   └── loader.py          # YAML policy loading & validation
│   ├── integrations/          # Model and framework wrappers
│   │   ├── gemini_wrapper.py  # GuardedGemini (primary integration)
│   │   ├── armoriq.py         # ArmorIQ intent enforcement
│   │   ├── langchain.py       # LangChain callback handler
│   │   └── llama_wrapper.py   # Local model wrapper
│   └── cli/
│       └── eval.py            # CLI tool: eval & benchmark commands
├── policies/                  # Pre-configured policies
│   ├── default.yaml           # Balanced general-purpose
│   ├── rag_strict.yaml        # High-risk RAG (healthcare/finance)
│   └── chatbot.yaml           # Low-latency chatbot
├── tests/                     # Unit tests
│   ├── test_heuristics.py
│   ├── test_embedding.py
│   ├── test_pipeline.py
│   ├── test_policy_loader.py
│   └── fixtures/
│       └── sample_traces.json # Canned test cases
├── eval/                      # Evaluation scripts
│   ├── run_halubench.py       # HaluBench benchmark runner
│   └── results/               # Evaluation output (JSON)
├── examples/
│   ├── gemini_rag_example.py       # Primary demo script
│   └── gemini_armoriq_example.py   # Two-layer stack demo
├── pyproject.toml
└── README.md
```

### Key Files

#### Core Engine
- **`hallucination_guard/__init__.py`**: Public API surface—exports `Guard`, `GuardDecision`, custom exceptions
- **`core/guard.py`**: Main entry point—`Guard` class with `validate()` and `validate_async()` methods
- **`core/pipeline.py`**: Three-tier cascade with early-exit logic and optional parallelization
- **`core/decision.py`**: Weighted score aggregation and decision mapping (allow/block/regenerate/abstain)
- **`core/trace.py`**: `GuardTrace` schema for Langfuse-compatible logging

#### Validators
- **`validators/base.py`**: `BaseValidator` abstract class, `ValidationInput`/`ValidationResult` schemas
- **`validators/heuristics.py`**: Tier 1—context coverage, entity overlap, length anomaly (target <5ms)
- **`validators/embedding.py`**: Tier 2—cosine similarity via all-MiniLM-L6-v2 (target <30ms)
- **`validators/hhem.py`**: Tier 3—HHEM 2.1-Open faithfulness classifier (target <80ms)
- **`validators/lynx.py`**: Phase 2 placeholder—always returns `is_available() = False` for MVP
- **`validators/safety.py`**: Optional safety classifier (Llama Guard, disabled by default)

#### Policy System
- **`policy/schema.py`**: Pydantic models—`ValidatorConfig`, `MitigationConfig`, `PolicyConfig`
- **`policy/loader.py`**: YAML policy loading with validation and in-memory caching

#### Integrations
- **`integrations/gemini_wrapper.py`**: `GuardedGemini`—wraps Gemini, validates output, handles regenerate logic
- **`integrations/armoriq.py`**: `ArmorIQAdapter`—pre-execution intent enforcement (stub mode if no client)
- **`integrations/langchain.py`**: `HallucinationGuardCallback`—LangChain RAG chain integration
- **`integrations/llama_wrapper.py`**: Wrapper for local models (llama-cpp-python, etc.)

#### Policies
- **`policies/default.yaml`**: Balanced policy for general-purpose apps
- **`policies/rag_strict.yaml`**: Strict policy for high-risk domains—lower threshold, regenerate on failure
- **`policies/chatbot.yaml`**: Relaxed policy for low-latency chatbots—heuristics + embeddings only

#### Examples & Eval
- **`examples/gemini_rag_example.py`**: Primary hackathon demo—shows blocked vs allowed responses
- **`examples/gemini_armoriq_example.py`**: Two-layer demo—text validation + action enforcement
- **`cli/eval.py`**: CLI tool—`hguard eval` (benchmark datasets) and `hguard benchmark` (latency)
- **`eval/run_halubench.py`**: Standalone HaluBench evaluation with precision/recall/F1 metrics

---

## Essential Commands

### Environment Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package in editable mode with all extras
pip install -e ".[gemini,langchain,observability,dev]"

# Install minimal runtime only
pip install -e .
```

### Development

```bash
# Format code
black hallucination_guard/ tests/ examples/

# Lint
ruff check hallucination_guard/ tests/ examples/
mypy hallucination_guard/

# Type check
mypy hallucination_guard/ --strict
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=hallucination_guard --cov-report=html

# Run specific test file
pytest tests/test_pipeline.py

# Run async tests only
pytest tests/ -k async

# Run tests without model downloads (fast mode)
HG_DISABLE_HHEM=true pytest tests/test_heuristics.py tests/test_embedding.py
```

### Evaluation & Benchmarking

```bash
# Run CLI evaluation on HaluBench
hguard eval --dataset halueval --policy rag_strict --output eval/results/halueval_run1.json

# Benchmark latency (p50/p95/p99)
hguard benchmark --requests 1000 --concurrency 10 --policy default

# Run standalone HaluBench evaluation
python eval/run_halubench.py --policy rag_strict --output eval/results/halubench_$(date +%Y%m%d).json
```

### Running Examples

```bash
# Primary demo (requires GOOGLE_API_KEY)
export GOOGLE_API_KEY=your_key_here
python examples/gemini_rag_example.py

# Two-layer demo (ArmorIQ + HallucinationGuard)
python examples/gemini_armoriq_example.py

# With Langfuse tracing enabled
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...
python examples/gemini_rag_example.py
```

### Model Management

```bash
# Pre-download models (optional, happens auto on first use)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; AutoModelForSequenceClassification.from_pretrained('vectara/hallucination_evaluation_model')"

# Clear model cache
rm -rf ~/.cache/huggingface/hub/models--vectara--hallucination_evaluation_model
rm -rf ~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2

# Check model cache size
du -sh ~/.cache/huggingface/
```

### Build & Distribution

```bash
# Build wheel
python -m build

# Install from wheel
pip install dist/hallucination_guard-*.whl

# Clean build artifacts
rm -rf build/ dist/ *.egg-info __pycache__
find . -type d -name __pycache__ -exec rm -rf {} +
```

---

## Patterns

### Typical SDK Usage Flow

```python
from hallucination_guard import Guard, HallucinationBlockedError

# Initialize guard with a policy
guard = Guard(policy="rag_strict")  # or path to custom YAML

# Validate output
decision = guard.validate(
    prompt="What is the capital of France?",
    output="The capital of France is Paris.",
    context="France is a country in Europe. Its capital city is Paris.",
    domain="geography"  # optional metadata
)

# Check decision
if decision.decision == "allow":
    print(f"✓ Safe to return (risk={decision.risk_score:.2f})")
    return decision.output
elif decision.decision == "block":
    print(f"✗ Blocked (risk={decision.risk_score:.2f}): {decision.evidence}")
    raise HallucinationBlockedError(decision.evidence)
elif decision.decision == "regenerate":
    print(f"↻ Regenerate with hint: {decision.suggested_fix}")
    # Re-prompt model with suggested_fix
```

### GuardedGemini Pattern (Primary Integration)

```python
from hallucination_guard.integrations import GuardedGemini
import google.generativeai as genai

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
base_model = genai.GenerativeModel("gemini-2.0-flash")

# Wrap with guard
guarded = GuardedGemini(
    model=base_model,
    policy="rag_strict",
    max_retries=2  # Auto-regenerate up to 2 times
)

# Generate with automatic validation
try:
    response = guarded.generate(
        prompt="Summarize this research paper.",
        context=paper_text
    )
    print(response.text)  # Only returned if validation passes
except HallucinationBlockedError as e:
    print(f"Blocked after retries: {e}")
```

### LangChain Integration Pattern

```python
from langchain.chains import RetrievalQA
from hallucination_guard.integrations import HallucinationGuardCallback

chain = RetrievalQA.from_chain_type(
    llm=llm,
    retriever=vector_store.as_retriever()
)

# Add guard as callback
guard_callback = HallucinationGuardCallback(policy="rag_strict")

result = chain.run(
    "What did the author say about AI safety?",
    callbacks=[guard_callback]
)

# Check guard decision in metadata
if result.metadata.get("guard_decision") == "block":
    print(f"Blocked: {result.metadata['guard_evidence']}")
```

### Custom Policy Creation

```yaml
# policies/my_custom_policy.yaml
name: "my_custom_policy"
description: "Tuned for medical Q&A"
latency_budget_ms: 150
risk_threshold: 0.3  # Lower = stricter

validators:
  - name: "heuristics"
    enabled: true
    weight: 0.2
    threshold: 0.5
    timeout_ms: 5
  
  - name: "embedding"
    enabled: true
    weight: 0.3
    threshold: 0.7
    timeout_ms: 30
  
  - name: "hhem"
    enabled: true
    weight: 0.5
    threshold: 0.8  # Stricter HHEM threshold
    timeout_ms: 100

mitigation:
  on_block: "regenerate"  # Auto-retry instead of hard block
  on_timeout: "allow"     # Allow if latency exceeded
  on_error: "abstain"     # Return "not enough info" on validator crash
```

### Writing New Validators

```python
from hallucination_guard.validators.base import BaseValidator, ValidationInput, ValidationResult

class MyCustomValidator(BaseValidator):
    def __init__(self, config: dict):
        super().__init__(config)
        self.threshold = config.get("threshold", 0.5)
        # Load any models or resources here
    
    def is_available(self) -> bool:
        """Check if validator can run (models loaded, deps available)."""
        return True  # or check for GPU, model files, etc.
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """
        Return a score in [0, 1] where:
        - 0.0 = definitely hallucinated
        - 1.0 = definitely faithful
        """
        # Your validation logic here
        score = self._compute_score(input.output, input.context)
        
        return ValidationResult(
            validator_name="my_custom",
            score=score,
            passed=score >= self.threshold,
            evidence=f"Custom check scored {score:.2f}",
            latency_ms=latency
        )
```

### Trace Export to Langfuse

```python
import os
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-..."
os.environ["LANGFUSE_SECRET_KEY"] = "sk-..."

# Traces auto-export when credentials are set
guard = Guard(policy="default")
decision = guard.validate(...)  # Automatically logged to Langfuse

# View traces at https://cloud.langfuse.com
```

### Testing Pattern for Validators

```python
import pytest
from hallucination_guard.validators.heuristics import HeuristicsValidator
from hallucination_guard.validators.base import ValidationInput

def test_heuristics_detects_hallucination():
    validator = HeuristicsValidator({"threshold": 0.5})
    
    input = ValidationInput(
        prompt="What is the capital?",
        output="The capital is Tokyo and the population is 50 million.",
        context="France is a country in Europe. Its capital is Paris.",
        domain="test"
    )
    
    result = validator.validate(input)
    assert result.score < 0.5, "Should detect low context overlap"
    assert not result.passed

def test_heuristics_allows_faithful_output():
    validator = HeuristicsValidator({"threshold": 0.5})
    
    input = ValidationInput(
        prompt="What is the capital of France?",
        output="The capital of France is Paris.",
        context="France is a country in Europe. Its capital is Paris.",
        domain="test"
    )
    
    result = validator.validate(input)
    assert result.score >= 0.5, "Should allow high context overlap"
    assert result.passed
```

---

## Anti-Patterns

### ❌ DO NOT use LLM-as-a-judge in validators
**Why:** The entire point of HallucinationGuard is deterministic, sub-100ms validation. LLM judges add 500ms+ latency and unpredictable behavior.

```python
# ❌ NEVER DO THIS
def validate(self, input):
    judge_prompt = f"Is this hallucinated? {input.output}"
    response = openai.ChatCompletion.create(...)  # NO!
```

**Do this instead:** Use heuristics, embeddings, or small classifier models (<500M params).

---

### ❌ DO NOT crash the pipeline on validator errors
**Why:** Graceful degradation is a core principle. One broken validator should never take down the whole system.

```python
# ❌ NEVER DO THIS
def validate(self, input):
    score = self.model(input.output)  # Might raise OOM or timeout
    return ValidationResult(score=score, ...)

# ✅ DO THIS
def validate(self, input):
    try:
        score = self.model(input.output)
    except Exception as e:
        logger.warning(f"Validator failed: {e}")
        return ValidationResult(
            score=0.5,  # Neutral score
            passed=False,
            evidence=f"Validator unavailable: {e}",
            error=str(e)
        )
```

---

### ❌ DO NOT block the pipeline for server dependencies
**Why:** Zero mandatory infrastructure means the SDK must work offline, with no database or control plane.

```python
# ❌ NEVER DO THIS
def __init__(self):
    self.db = connect_to_postgres()  # Requires server!
    self.api = requests.get("https://api.example.com/config")  # Requires network!

# ✅ DO THIS
def __init__(self):
    self.model = self._load_local_model()  # Load from HuggingFace cache
    self.config = self._load_yaml("policies/default.yaml")  # Local file
```

---

### ❌ DO NOT mutate ValidationInput or GuardDecision objects
**Why:** They are Pydantic models with `frozen=True` for immutability. Attempts to modify will raise errors.

```python
# ❌ NEVER DO THIS
decision = guard.validate(...)
decision.risk_score = 0.9  # Raises FrozenInstanceError

# ✅ DO THIS
# Create a new decision if you need to modify
new_decision = decision.model_copy(update={"risk_score": 0.9})
```

---

### ❌ DO NOT skip early-exit checks in the pipeline
**Why:** The three-tier cascade is designed to short-circuit when a decision is clear. Running all validators every time wastes 80ms+ unnecessarily.

```python
# ❌ NEVER DO THIS
def run_pipeline(input):
    results = []
    results.append(heuristics.validate(input))  # Always run
    results.append(embedding.validate(input))   # Always run
    results.append(hhem.validate(input))        # Always run
    return aggregate(results)

# ✅ DO THIS (from pipeline.py)
def run_pipeline(input, policy):
    results = []
    
    # Tier 1
    h_result = heuristics.validate(input)
    results.append(h_result)
    if h_result.score < 0.2:  # Clearly bad
        return Decision(decision="block", ...)
    if h_result.score > 0.9:  # Clearly good
        return Decision(decision="allow", ...)
    
    # Tier 2 (only if Tier 1 uncertain)
    e_result = embedding.validate(input)
    results.append(e_result)
    # ... repeat early-exit logic
```

---

### ❌ DO NOT use ArmorIQ for text validation
**Why:** ArmorIQ is for intent enforcement (actions), not hallucination detection (text). Keep responsibilities separate.

```python
# ❌ NEVER DO THIS
def validate_text(output):
    armoriq.enforce(task="validate", action=output)  # Wrong layer!

# ✅ DO THIS
# HallucinationGuard validates text
decision = guard.validate(prompt, output, context)
if decision.decision != "allow":
    raise HallucinationBlockedError()

# ArmorIQ validates actions (after text passes)
if action_required:
    armoriq.enforce(user_task="book flight", action_plan=tool_call)
```

---

### ❌ DO NOT hardcode policy thresholds in code
**Why:** Policies should be tunable via YAML files without code changes. Enables domain-specific tuning and A/B testing.

```python
# ❌ NEVER DO THIS
class HHEMValidator:
    def __init__(self):
        self.threshold = 0.8  # Hardcoded!

# ✅ DO THIS
class HHEMValidator:
    def __init__(self, config: ValidatorConfig):
        self.threshold = config.threshold  # From YAML policy
```

---

### ❌ DO NOT assume context is always provided
**Why:** Some use cases (chatbots, creative writing) don't have reference context. Validators must handle `context=None` gracefully.

```python
# ❌ NEVER DO THIS
def validate(self, input):
    overlap = count_overlap(input.context, input.output)  # Crashes if context is None!

# ✅ DO THIS
def validate(self, input):
    if input.context is None:
        return ValidationResult(score=0.5, evidence="No context provided, skipping check")
    overlap = count_overlap(input.context, input.output)
```

---

### ❌ DO NOT log sensitive data in traces
**Why:** Traces may contain PII or proprietary information. Sanitize before exporting to Langfuse or writing to disk.

```python
# ❌ NEVER DO THIS
trace = GuardTrace(
    prompt=user_prompt,  # Might contain SSN, emails, etc.
    output=model_output,
    ...
)
langfuse.log(trace)

# ✅ DO THIS
trace = GuardTrace(
    prompt=sanitize(user_prompt),  # Redact PII first
    output=sanitize(model_output),
    ...
)
```

---

## Code Style

- Follow **PEP 8** for all Python code
- Use **Black** for formatting (line length 100)
- Use **Ruff** for linting
- Use **mypy** with `--strict` for type checking
- All public APIs must have docstrings (Google style)
- Prefer explicit over implicit (no magic, no monkey-patching)
- Use Pydantic models for all data schemas (policies, results, traces)
- Use `logger.warning()` for degraded mode, `logger.error()` only for true errors
- Never use `print()` in library code—use structured logging
- Async functions must be suffixed with `_async` (e.g., `validate_async()`)

---

## Commit and Pull Request Guidelines

### Pre-Commit Validation (REQUIRED)

Before committing any code, you MUST run these checks and fix all failures:

```bash
# 1. Format
black hallucination_guard/ tests/ examples/

# 2. Lint
ruff check hallucination_guard/ tests/ examples/ --fix

# 3. Type check
mypy hallucination_guard/ --strict

# 4. Run tests
pytest

# 5. Verify no secrets committed
git diff --cached | grep -i "api.key\|secret\|password" && echo "❌ SECRETS DETECTED" || echo "✓ No secrets found"
```

All checks must pass before commit. Do not bypass with `--no-verify`.

### Commit Message Format

Use conventional commit format: `type: message`

**Types:**
- `feat`: New feature (e.g., `feat: add Lynx validator`)
- `fix`: Bug fix (e.g., `fix: handle None context in embedding validator`)
- `docs`: Documentation only (e.g., `docs: update policy YAML examples`)
- `test`: Add or update tests (e.g., `test: add pipeline early-exit tests`)
- `refactor`: Code change with no behavior change (e.g., `refactor: extract score aggregation`)
- `perf`: Performance improvement (e.g., `perf: cache HHEM model loading`)
- `chore`: Build/tooling/dependencies (e.g., `chore: bump transformers to 4.44`)

**Examples:**
```
feat: add streaming support to GuardedGemini
fix: graceful degradation on HHEM timeout
docs: add LangChain integration example
test: add fixtures for rag_strict policy
perf: parallelize Tier 2 and Tier 3 validators
```

### Pull Request Requirements

**Before opening a PR:**
1. All pre-commit checks pass
2. New features have unit tests (min 80% coverage for new code)
3. Breaking changes documented in PR description
4. Validators have benchmark latency numbers in PR description
5. Policy changes tested on HaluBench subset

**PR Title:** Same format as commit messages (`type: description`)

**PR Description Template:**
```markdown
## Summary
Brief description of what this PR does.

## Changes
- Bullet list of key changes

## Testing
- [ ] Unit tests added/updated
- [ ] Manual testing completed
- [ ] Latency benchmark run (for validators): p95 = X ms

## Breaking Changes
List any breaking API changes, or "None"

## Benchmark Results (if applicable)
| Metric | Before | After |
|--------|--------|-------|
| p95 latency | X ms | Y ms |
| HaluBench F1 | X.XX | Y.YY |
```

### Branch Naming
- Feature: `feat/short-description` (e.g., `feat/armoriq-integration`)
- Fix: `fix/issue-description` (e.g., `fix/hhem-timeout`)
- Docs: `docs/what-changed` (e.g., `docs/add-quickstart`)

---

## Environment Variables Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_API_KEY` | — | Gemini API key for `GuardedGemini` (required for examples) |
| `HG_TRACE_DIR` | `~/.hallucination_guard/traces/` | Directory for JSONL trace logs |
| `HG_MODEL_CACHE` | `~/.cache/huggingface/` | HuggingFace model download cache |
| `HG_DEFAULT_POLICY` | `default` | Policy loaded when `Guard()` called without policy arg |
| `HG_DISABLE_HHEM` | `false` | Set `true` to skip HHEM (fast mode, heuristics + embeddings only) |
| `HG_LOG_LEVEL` | `WARNING` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LANGFUSE_PUBLIC_KEY` | — | Enables Langfuse trace export when set (with `LANGFUSE_SECRET_KEY`) |
| `LANGFUSE_SECRET_KEY` | — | Langfuse authentication secret |

---

## Non-Negotiable Rules (STOP AND ASK FIRST)

These rules cannot be violated without explicit permission:

1. **No LLM-as-a-judge calls** anywhere in the runtime validation pipeline
2. **No mandatory server infrastructure**—must work offline with local models only
3. **Graceful degradation always**—validator failures return neutral scores, never crash
4. **Gemini generates, HallucinationGuard validates, ArmorIQ enforces**—no responsibility overlap
5. **All public APIs are immutable Pydantic models**—no in-place mutation
6. **All validators inherit from `BaseValidator`** and implement `validate(ValidationInput) -> ValidationResult`
7. **All policy files are valid YAML** and validate against `PolicyConfig` schema
8. **Target latency is p95 < 100ms**—any change that regresses this must be justified
9. **All models are auto-downloaded from HuggingFace**—no manual model file management
10. **No secrets in code or git history**—use environment variables only

If you need an exception to ANY of these rules, STOP and get permission first.
