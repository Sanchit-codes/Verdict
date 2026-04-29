# ⚖️ Verdict

> **Vendor-neutral SDK for preventing AI hallucinations in production through inline validation—without slow LLM-as-a-judge calls.**

Verdict acts as a shield between your generative AI models and your users. By validating AI-generated text using a deterministic three-tier cascade, it ensures factual consistency, context adherence, and safety before the response is ever returned to the end user.

---

## ✨ Core Value Proposition

- **No LLM-as-a-judge**: LLM judges add 500ms+ latency and unpredictable behavior. Verdict relies on heuristics, embeddings, and small classifier models (<500M params).
- **Sub-100ms Latency**: Target p95 latency is under 100ms across all tiers, optimized for CPU-only deployments.
- **Zero Mandatory Infrastructure**: A pure Python library. No databases, vector stores, or control planes required.
- **Graceful Degradation**: One broken validator never takes down the whole system.
- **Vendor-Neutral**: Plug-and-play with any provider (Gemini, OpenAI, Anthropic, or local models).
- **ArmorIQ Integration**: Optional pre-execution intent enforcement layer to stop bad agent actions.

---

## 🏗️ The 3-Tier Validation Cascade

Verdict evaluates responses using an early-exit pipeline to save compute:

1. **Tier 1: Heuristics (<5ms)**
   - Context coverage ratios, entity overlap checks, and length anomalies.
   - *If clearly hallucinated or clearly faithful, it exits here.*
2. **Tier 2: Embedding Similarity (<30ms)**
   - Cosine similarity matching between the prompt/context and the output using `all-MiniLM-L6-v2`.
3. **Tier 3: Faithfulness Classifier (<80ms)**
   - Deep semantic analysis using the `HHEM 2.1-Open` model to catch subtle factual inconsistencies.

---

## 🚀 Quick Start

### Python SDK

```bash
# Install the core library
pip install -e .

# Or install with all integrations (Gemini, LangChain, Observability)
pip install -e ".[all]"
```

```python
from verdict import Guard

# Initialize the guard with a default YAML policy
guard = Guard(policy="rag_strict")

decision = guard.validate(
    prompt="What is the capital of France?",
    output="The capital of France is Paris.",
    context="France is a country in Europe. Its capital city is Paris."
)

if decision.decision == "allow":
    print("✓ Safe to return to user!")
else:
    print(f"✗ Blocked: {decision.evidence}")
```

### Node.js SDK & API Server

If you're building a TypeScript/JavaScript backend, run the Verdict API server alongside your app.

```bash
# 1. Start the Python API Server
python server/run.py
```

```bash
# 2. Install the Node SDK in your JS project
npm install verdict-node-sdk
```

```typescript
import { VerdictClient } from 'verdict-node-sdk';

const client = new VerdictClient({ baseUrl: 'http://localhost:5000' });

const decision = await client.validate({
  prompt: 'Who won the 2022 World Cup?',
  output: 'Argentina won the 2022 World Cup.',
  context: 'The 2022 FIFA World Cup was won by Argentina.'
});

console.log(decision.decision); // 'allow'
```

---

## 📂 Project Structure

Verdict is a monorepo containing the core Python SDK, an API server, and multi-language SDK clients.

```text
Verdict/
├── src/                  # Core Python SDK package ('verdict')
│   ├── core/             # Validation engine, pipelines, trace logic
│   ├── validators/       # Heuristics, Embedding, and HHEM implementations
│   ├── policy/           # YAML configuration loader & schemas
│   ├── integrations/     # Wrappers for Gemini, Langchain, and ArmorIQ
│   └── cli/              # CLI evaluation tools
├── server/               # Flask REST API Server for remote validation
├── sdks/node/            # Node.js/TypeScript SDK client
├── tests/                # Consolidated unit and integration test suite
└── Makefile              # Development commands
```

---

## 🛠️ Configuration & Policies

Policies define the strictness of the guardrails. They are configured via YAML files, allowing domain-specific tuning (e.g., highly strict for healthcare, relaxed for creative chatbots).

```yaml
# src/policy/defaults/rag_strict.yaml
name: "rag_strict"
risk_threshold: 0.3

validators:
  - name: "heuristics"
    weight: 0.2
    threshold: 0.5
  - name: "hhem"
    weight: 0.5
    threshold: 0.8  # Stricter requirement for high-risk domains
```

---

## 🤝 Contributing

Contributions are welcome! Please check out [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. 

### Development Setup
```bash
# Setup virtual environment and install dev dependencies
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
make test

# Format code
make format
```

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
