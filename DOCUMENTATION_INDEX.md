# GuardlyAI Documentation Index

**Welcome to GuardlyAI!** This is your guide to the complete documentation for the hallucination detection and prevention system.

## 🚀 Getting Started (Start Here!)

| Document | Time | Purpose |
|----------|------|---------|
| **[README.md](README.md)** | 5 min | Project overview, feature list, architecture |
| **[QUICKSTART.md](QUICKSTART.md)** | 10 min | Installation, setup, first API call |
| **[GEMINI_SETUP.md](GEMINI_SETUP.md)** | 5 min | Get Google API key, enable generation feature |

## 📋 Project Documentation

| Document | Status | Details |
|----------|--------|---------|
| **[PROJECT_COMPLETION_SUMMARY.md](PROJECT_COMPLETION_SUMMARY.md)** | ✅ NEW | 4 phases, all features, performance metrics |
| **[GEMINI_INTEGRATION_SUMMARY.md](GEMINI_INTEGRATION_SUMMARY.md)** | ✅ NEW | Gemini integration details, architecture, examples |
| **[INTEGRATION_COMPLETE.md](INTEGRATION_COMPLETE.md)** | ✅ Complete | Frontend + backend integration summary |
| **[TEST_EXECUTION_REPORT.txt](TEST_EXECUTION_REPORT.txt)** | ✅ Complete | Detailed E2E test results (12/12 passed) |
| **[TEST_SUMMARY.md](TEST_SUMMARY.md)** | ✅ Complete | Quick test overview and status |

## 🔌 Technical Documentation

| Document | Audience | Content |
|----------|----------|---------|
| **[API_REFERENCE.md](API_REFERENCE.md)** | Developers | All 5 endpoints, curl/Python/TypeScript examples |
| **[SDK_INTEGRATION_GUIDE.md](SDK_INTEGRATION_GUIDE.md)** | Backend integrators | Architecture, patterns, deployment |
| **[CODEBASE_CONTEXT.md](CODEBASE_CONTEXT.md)** | Code maintainers | Deep dive into SDK architecture |
| **[AGENTS.md](AGENTS.md)** | AI agents | Agent instructions and guidelines |

## 📚 Implementation Guides

| Document | Focus | Who Should Read |
|----------|-------|-----------------|
| **[EXAMPLES.md](EXAMPLES.md)** | Real-world use cases | Integration engineers |
| **[examples/gemini_validation_demo.py](examples/gemini_validation_demo.py)** | Working demo | Everyone trying it out |
| **[guardly-node-sdk/USAGE.md](guardly-node-sdk/USAGE.md)** | Node.js SDK | Frontend/Node developers |

## 🛠️ Operations & Deployment

| Document | Purpose | Audience |
|----------|---------|----------|
| **[server/README.md](server/README.md)** | Flask backend setup | DevOps, backend ops |
| **[STARTUP_SCRIPTS.md](STARTUP_SCRIPTS.md)** | Local dev startup | Developers |
| **[INTEGRATION_TEST.md](INTEGRATION_TEST.md)** | Manual test scenarios | QA, testers |

## 📊 Performance & Optimization

| Document | Details | Status |
|----------|---------|--------|
| **[OPTIMIZATION_COMPLETE.md](OPTIMIZATION_COMPLETE.md)** | Latency tuning | ✅ Complete (p95 < 150ms) |
| **[PERFORMANCE_OPTIMIZATIONS.md](PERFORMANCE_OPTIMIZATIONS.md)** | Caching, batching | ✅ Documented |

## 🎯 Quick Reference by Use Case

### "I want to set up GuardlyAI locally"
1. Start → [QUICKSTART.md](QUICKSTART.md) (10 min)
2. Then → [GEMINI_SETUP.md](GEMINI_SETUP.md) (5 min)
3. Run → `python examples/gemini_validation_demo.py`

### "I want to understand the system"
1. Read → [README.md](README.md) (overview)
2. Read → [PROJECT_COMPLETION_SUMMARY.md](PROJECT_COMPLETION_SUMMARY.md) (full details)
3. Review → [API_REFERENCE.md](API_REFERENCE.md) (endpoints)

### "I want to integrate GuardlyAI into my project"
1. Review → [API_REFERENCE.md](API_REFERENCE.md) (endpoints)
2. Follow → [SDK_INTEGRATION_GUIDE.md](SDK_INTEGRATION_GUIDE.md) (patterns)
3. Copy → Example code from [EXAMPLES.md](EXAMPLES.md)

### "I want to deploy to production"
1. Setup → [server/README.md](server/README.md) (Flask)
2. Configure → Environment variables section below
3. Deploy → Using Gunicorn/Docker instructions in server/README.md

### "I want to test the system"
1. Run → `pytest tests/` (unit tests)
2. Follow → [INTEGRATION_TEST.md](INTEGRATION_TEST.md) (manual E2E)
3. Review → [TEST_EXECUTION_REPORT.txt](TEST_EXECUTION_REPORT.txt) (what was tested)

## 🗂️ Directory Structure

```
GuardlyAI/
├── README.md                          ← START HERE
├── QUICKSTART.md                      ← 5-minute setup
├── GEMINI_SETUP.md                    ← Google API key setup
├── PROJECT_COMPLETION_SUMMARY.md      ← Full project overview
├── GEMINI_INTEGRATION_SUMMARY.md      ← Phase 4 details
├── API_REFERENCE.md                   ← All endpoints
├── DOCUMENTATION_INDEX.md             ← This file
│
├── hallucination_guard/               # Python SDK (core)
│   ├── core/
│   │   ├── guard.py                  # Main Guard class
│   │   ├── pipeline.py               # 3-tier validation
│   │   └── decision.py               # Score aggregation
│   ├── validators/
│   │   ├── heuristics.py            # Tier 1
│   │   ├── embedding.py             # Tier 2
│   │   └── hhem.py                  # Tier 3
│   └── policy/
│       └── loader.py                # YAML policy loading
│
├── server/                            # Flask REST API
│   ├── __init__.py
│   ├── config.py
│   ├── routes.py                     # /api/validate, /api/generate, etc.
│   ├── gemini_generator.py           # NEW: Gemini wrapper
│   ├── run.py                        # Entry point
│   └── README.md                     # Deployment guide
│
├── GuardlyFrontend/                   # Next.js UI
│   └── src/
│       ├── app/page.tsx              # Chat UI
│       ├── lib/guardly-client.ts     # SDK wrapper
│       └── hooks/useGuardly.ts       # React hook
│
├── examples/
│   ├── gemini_validation_demo.py     # Standalone demo
│   └── (other examples)
│
├── tests/                             # 39+ unit tests
├── policies/                          # YAML policy files
└── docs/                              # Additional docs

Documentation Files (This Directory):
├── QUICKSTART.md
├── GEMINI_SETUP.md
├── GEMINI_INTEGRATION_SUMMARY.md
├── PROJECT_COMPLETION_SUMMARY.md
├── API_REFERENCE.md
├── SDK_INTEGRATION_GUIDE.md
├── EXAMPLES.md
├── DOCUMENTATION_INDEX.md ← You are here
├── TEST_EXECUTION_REPORT.txt
├── TEST_SUMMARY.md
├── INTEGRATION_COMPLETE.md
├── INTEGRATION_TEST.md
├── STARTUP_SCRIPTS.md
└── (more...)
```

## 📖 Document Descriptions

### README.md
The main project document covering:
- Project overview and value proposition
- Feature list
- System architecture
- Quick start
- Tech stack
- Core concepts

### QUICKSTART.md
5-minute setup guide:
- Prerequisites
- Installation
- Configuration
- First API call
- Troubleshooting

### GEMINI_SETUP.md
Google Gemini integration guide:
- Get API key (free tier details)
- Install with Gemini support
- Set environment variables
- Run demo
- Common issues and fixes

### PROJECT_COMPLETION_SUMMARY.md
Comprehensive project overview:
- All 4 phases explained
- Complete architecture
- File structure
- Test results
- Performance metrics
- Deployment options
- Configuration reference

### GEMINI_INTEGRATION_SUMMARY.md
Phase 4 (Gemini) implementation details:
- Backend: GeminiGenerator, /api/generate
- Frontend: generateAndValidate() method
- Demo script walkthrough
- API examples
- Error handling

### API_REFERENCE.md
Complete API documentation:
- All 5 endpoints (/validate, /batch, /generate, /health, /version)
- Request/response schemas
- Error codes and handling
- curl, Python, and TypeScript examples
- Quick reference table

### SDK_INTEGRATION_GUIDE.md
Backend architecture and integration:
- How Guard works
- Three-tier validation pipeline
- Decision logic
- Policy configuration
- Integration patterns
- Deployment considerations

### EXAMPLES.md
Real-world usage examples:
- Python integration
- Node.js/TypeScript integration
- RAG chain integration
- LangChain callbacks
- Custom policies
- Error handling patterns

### CODEBASE_CONTEXT.md
Deep dive into the Python SDK:
- Validator implementations
- Policy loading system
- Decision engine
- Error handling
- Testing patterns
- Architecture decisions

### AGENTS.md
Instructions for AI agents:
- Project overview
- Technical stack
- Design principles
- Key files reference
- Anti-patterns
- Commit message format
- Non-negotiable rules

### TEST_EXECUTION_REPORT.txt
Detailed E2E test results:
- 12 test scenarios executed
- Pass/fail status for each
- Performance measurements
- Component verification
- System architecture validation
- Recommendations

### TEST_SUMMARY.md
Quick test overview:
- Total tests: 12
- Pass rate: 100%
- Status: Production Ready
- List of tested features
- Performance metrics

## 🔑 Key Concepts

### Three-Tier Validation Cascade
1. **Tier 1 - Heuristics** (<1ms): Fast deterministic checks
   - Context coverage ratio
   - Entity overlap
   - Length anomalies

2. **Tier 2 - Embeddings** (<30ms): Semantic similarity
   - All-MiniLM-L6-v2 model
   - Cosine similarity to context

3. **Tier 3 - HHEM Classifier** (<80ms): ML-based faithfulness
   - Vectara hallucination model
   - Fine-tuned on diverse domains

### Decision Types
- **ALLOW** (✅): Risk < 0.30 - Safe to use
- **BLOCK** (✗): Risk > 0.70 - Likely hallucination
- **REGENERATE** (⚠️): 0.30 ≤ risk ≤ 0.70 - Try again
- **ABSTAIN** (❓): Unable to decide - Graceful degradation

### Policy System
YAML-based configuration:
- Validator weights and thresholds
- Decision mappings (risk score → decision)
- Mitigation strategies (timeout behavior)
- Three pre-configured policies:
  - `default`: Balanced
  - `rag_strict`: High-risk domains
  - `chatbot`: Low-latency

## ⚙️ Configuration

### Environment Variables
```bash
# Backend
export PORT=5000
export FLASK_ENV=development
export CORS_ORIGIN=http://localhost:3000
export GOOGLE_API_KEY=your_api_key
export GEMINI_MODEL=gemini-2.5-flash
export GEMINI_TEMPERATURE=0.7
export GEMINI_MAX_TOKENS=1024

# Frontend
export NEXT_PUBLIC_GUARDLY_API=http://localhost:5000/api
export NEXT_PUBLIC_GUARDLY_POLICY=default
```

### Running Services
```bash
# Backend (Flask)
python server/run.py

# Frontend (Next.js)
cd GuardlyFrontend
npm run dev

# Both (automated script)
./start-all.sh
```

## 🧪 Testing

```bash
# Unit tests
pytest tests/ -v

# Specific test file
pytest tests/test_guard.py -v

# With coverage
pytest --cov=hallucination_guard

# Frontend
cd GuardlyFrontend
npm run build      # Type check
npm test          # Unit tests
```

## 📊 Project Status

| Component | Status | Tests | Docs |
|-----------|--------|-------|------|
| HallucinationGuard SDK | ✅ Complete | 92+ passing | ✅ |
| Node.js Client SDK | ✅ Complete | 40 passing | ✅ |
| Flask REST API | ✅ Complete | 26 integration | ✅ |
| Next.js Frontend | ✅ Complete | 12 E2E | ✅ |
| Gemini Integration | ✅ Complete | All passing | ✅ |
| **TOTAL** | **✅ READY** | **39/39 + 12/12** | **12 docs** |

## 🚀 Next Steps

1. **Read**: [QUICKSTART.md](QUICKSTART.md) (10 minutes)
2. **Setup**: Follow instructions to get API key and start services
3. **Test**: Visit http://localhost:3000 and try a message
4. **Integrate**: Use examples from [EXAMPLES.md](EXAMPLES.md)
5. **Deploy**: Follow [server/README.md](server/README.md) for production

## 💬 Questions?

1. Check the relevant documentation above
2. Search in [API_REFERENCE.md](API_REFERENCE.md) or [EXAMPLES.md](EXAMPLES.md)
3. Review [AGENTS.md](AGENTS.md) for development patterns
4. Run tests: `pytest tests/` or `npm test`

---

**Last Updated**: 2026-04-05  
**Status**: 🟢 Production Ready  
**Version**: 1.0.0

See [PROJECT_COMPLETION_SUMMARY.md](PROJECT_COMPLETION_SUMMARY.md) for full project details.

