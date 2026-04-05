# Gemini Integration Setup Guide

Get started with Google Gemini and HallucinationGuard in **5 minutes**. This guide covers API key setup, installation, and running the validation demo.

## Prerequisites

- **Python**: 3.10 or higher
- **pip** or **poetry** for package management
- **Google account** (free tier available)

## Step 1: Get Your Google API Key (2 minutes)

HallucinationGuard works with Google Gemini for text generation. You need a free API key.

### Option A: Quick Setup (Recommended)

1. Go to **[Google AI Studio](https://aistudio.google.com/apikey)**
2. Click **"Create API Key"** (blue button)
3. Copy the key and save it somewhere safe
4. You now have a free quota: 15 requests per minute, 1,500 requests per day

### Option B: Production Setup

For production deployments, use Google Cloud:

1. Create a [Google Cloud project](https://console.cloud.google.com/project)
2. Enable the **Generative Language API**
3. Create a service account and JSON key
4. Set `GOOGLE_API_KEY` to your credentials

> ⚠️ **Keep your API key secret!** Never commit it to git. Use environment variables only.

## Step 2: Install Dependencies (1 minute)

Install HallucinationGuard with Gemini support:

```bash
# Basic install (minimal deps)
pip install hallucination-guard google-generativeai

# Full install (with observability & dev tools)
pip install hallucination-guard[gemini,observability,dev]
```

**What each extra includes:**
- `[gemini]` → Google Generativeai SDK
- `[observability]` → Langfuse tracing (optional)
- `[dev]` → pytest, black, ruff (for development)

## Step 3: Set Your API Key (30 seconds)

Store your API key as an environment variable:

```bash
# On macOS/Linux
export GOOGLE_API_KEY="your_key_from_step_1"

# On Windows (PowerShell)
$env:GOOGLE_API_KEY="your_key_from_step_1"

# On Windows (Command Prompt)
set GOOGLE_API_KEY=your_key_from_step_1
```

**Or** create a `.env` file in your project root:

```bash
# .env
GOOGLE_API_KEY=your_key_here
```

Then load it before running Python:

```python
from dotenv import load_dotenv
load_dotenv()
```

## Step 4: Run the Demo (1 minute)

Run the complete Gemini + validation demo:

```bash
python examples/gemini_validation_demo.py
```

Expected output:

```
════════════════════════════════════════════════════════════════════════════════
Gemini + HallucinationGuard Demo
Generate text with Gemini, validate with 3-tier cascade
════════════════════════════════════════════════════════════════════════════════

Setting up Gemini and HallucinationGuard...
✓ Setup complete

════════════════════════════════════════════════════════════════════════════════
Active Policy Configuration
════════════════════════════════════════════════════════════════════════════════

Policy Settings
┌──────────────┬─────────────────────────────────────────────────────────────┐
│ Property     │ Value                                                       │
├──────────────┼─────────────────────────────────────────────────────────────┤
│ Policy Name  │ default                                                     │
│ Description  │ Balanced policy for general-purpose applications...         │
│ Risk Thresh  │ 0.50                                                        │
│ Latency Budg │ 150ms                                                       │
└──────────────┴─────────────────────────────────────────────────────────────┘

Validators (3-Tier Cascade):
✓ Tier 1: HEURISTICS
   Weight: 20.0% | Threshold: 0.50 | Timeout: 5ms
✓ Tier 2: EMBEDDING
   Weight: 30.0% | Threshold: 0.70 | Timeout: 30ms
✓ Tier 3: HHEM
   Weight: 50.0% | Threshold: 0.75 | Timeout: 100ms

Running validation demos...
Each case generates text with Gemini and validates with HallucinationGuard

════════════════════════════════════════════════════════════════════════════════
Case 1: Faithful Output (Expected: ALLOWED)
════════════════════════════════════════════════════════════════════════════════

[Case 1 output...]
```

The demo will:
1. **Generate** text for 3 different scenarios using Gemini 2.5 Flash
2. **Validate** each output with the 3-tier cascade
3. **Display** decisions (✓ ALLOW, ✗ BLOCK, ? ABSTAIN)

## Quick Example: Code Usage

Use HallucinationGuard with Gemini in your own code:

```python
import os
import google.generativeai as genai
from hallucination_guard import Guard

# Setup
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")
guard = Guard(policy="default")

# Generate with Gemini
context = "The Earth orbits the Sun and takes 365 days to complete one orbit."
prompt = "How long does Earth take to orbit the Sun?"
response = model.generate_content(f"Context: {context}\n\nQuestion: {prompt}")
output = response.text

# Validate with HallucinationGuard
decision = guard.validate(
    prompt=prompt,
    output=output,
    context=context
)

# Check result
if decision.decision == "allow":
    print(f"✓ Safe to return (risk={decision.risk_score:.2f})")
    return output
elif decision.decision == "block":
    print(f"✗ Hallucination detected (risk={decision.risk_score:.2f})")
    # Handle blocked output (e.g., regenerate, return error)
elif decision.decision == "abstain":
    print(f"? Manual review needed (uncertain)")
    # Escalate to human review
```

## Troubleshooting

### "GOOGLE_API_KEY not found"

```bash
# Check if environment variable is set
echo $GOOGLE_API_KEY  # macOS/Linux
echo %GOOGLE_API_KEY%  # Windows

# If empty, set it:
export GOOGLE_API_KEY="your_key_here"
```

### "ModuleNotFoundError: No module named 'google'"

```bash
# Install missing dependency
pip install google-generativeai
```

### "API quota exceeded"

You hit the free tier limit (15 req/min, 1,500/day). Solutions:

- **Wait** 1 minute and try again
- **Upgrade to paid** at [Google Cloud Console](https://console.cloud.google.com/billing)
- **Use a different API key**

### "Validation latency too slow (>100ms)"

The 3-tier cascade is designed for p95 <100ms on CPU. If running on:

- **Laptop/dev machine**: This is expected (cold-start, single model)
- **Production**: Use a GPU or cache models with `HG_DISABLE_HHEM=true`

Check individual tier latencies in the response:

```python
decision = guard.validate(...)
for result in decision.tier_results:
    print(f"{result.validator_name}: {result.latency_ms:.1f}ms")
```

### "Models downloading slowly"

Models are auto-downloaded on first use (~400MB total). To pre-download:

```bash
python -c "from hallucination_guard.validators.hhem import preload_hhem; preload_hhem()"
python -c "from hallucination_guard.validators.embedding import preload_embedding; preload_embedding()"
```

## Next Steps

- **Production**: See [Deployment Guide](../docs/DEPLOYMENT.md)
- **Advanced**: [ArmorIQ Integration](../examples/gemini_armoriq_example.py) for action enforcement
- **RAG**: [RAG Example](../examples/gemini_rag_example.py) for retrieval-augmented generation
- **LangChain**: [LangChain Integration](../docs/NODE_SDK_USAGE.md)

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | — | **Required.** Your Google Gemini API key |
| `HG_DEFAULT_POLICY` | `default` | Policy to use for validation (default, rag_strict, chatbot) |
| `HG_DISABLE_HHEM` | `false` | Skip Tier 3 for faster validation (heuristics + embeddings only) |
| `HG_LOG_LEVEL` | `WARNING` | Logging level: DEBUG, INFO, WARNING, ERROR |

## Support

**Issues?** Check these resources:

- [HallucinationGuard API Reference](../API_REFERENCE.md)
- [Common Issues FAQ](../QUICKSTART.md#troubleshooting)
- [GitHub Issues](https://github.com/guardly/guardly-ai/issues)

---

**That's it!** You're ready to generate with Gemini and validate with HallucinationGuard. 🚀
