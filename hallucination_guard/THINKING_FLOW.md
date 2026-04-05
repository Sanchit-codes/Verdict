# ArmorIQ Thinking Process Interception Flow

## Overview

This document describes the enhanced HallucinationGuard pipeline that intercepts the LLM's thinking process **before** running the validation cascade, enabling ArmorIQ to catch intent violations at the reasoning level.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ User Prompt                                                 │
│ "Book a flight to Paris under $500"                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Prompt Analysis & Ground Truth Creation            │
│                                                             │
│ • Tokenization & compaction                                │
│ • Intent extraction: "book flight"                          │
│ • Entity extraction: ["Paris", "$500"]                      │
│ • Domain inference: "travel"                                │
│ • Constraint extraction: ["under $500", "to Paris"]         │
│                                                             │
│ Output: GroundTruthContext (stored in Guard._ground_truth_store)
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Gemini Response Generation                         │
│                                                             │
│ • Call gemini-2.5-flash with prompt                        │
│ • Response includes thinking process + final text          │
│                                                             │
│ Output: GenerateContentResponse with:                       │
│   - thinking: "<think>Let me search flights DB</think>"     │
│   - text: "Paris flights found..."                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: EARLY ARMORIQ CHECK (NEW!)                         │
│ **This runs BEFORE validation cascade**                     │
│                                                             │
│ 1. Extract thinking from response:                          │
│    thinking = "Let me search flights database"              │
│                                                             │
│ 2. Retrieve ground truth task:                              │
│    task = "Book a flight to Paris under $500"              │
│                                                             │
│ 3. ArmorIQ enforces intent alignment:                       │
│    ✓ Thinking aligns with task → proceed                   │
│    ✗ Thinking violates task → BLOCK immediately            │
│                                                             │
│ Example violations caught here:                             │
│  - Thinking: "DELETE FROM users" → BLOCKED                 │
│  - Thinking: "Send data to attacker.com" → BLOCKED          │
│  - Thinking: "Book flight to Tokyo" → BLOCKED (wrong city)  │
│                                                             │
│ Output: IntentViolationError (if misaligned)                │
└────────────────────────┬────────────────────────────────────┘
                         │
         ✓ PASS          │          ✗ FAIL
                         │
         ┌───────────────┴──────────────┐
         │                              │
         ▼                              ▼
┌──────────────────────┐      ┌──────────────────────┐
│ STAGE 4:             │      │ BLOCKED              │
│ Text Validation      │      │                      │
│ Cascade              │      │ Raise IntentViolationError
│                      │      │ (Thinking caught bad  │
│ Tier 1: Heuristics   │      │  intent early)        │
│ Tier 2: Embeddings   │      └──────────────────────┘
│ Tier 3: HHEM         │
│                      │
│ Output: GuardDecision│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ STAGE 5:             │
│ Final Decision       │
│                      │
│ ✓ Allow             │
│ ✗ Block             │
│ ↻ Regenerate        │
│ ? Abstain           │
└──────────────────────┘
```

---

## Code Flow

### 1. Ground Truth Storage (In-Memory)

**File**: `hallucination_guard/core/guard.py`

```python
class Guard:
    # Class-level storage: session_key → GroundTruthContext
    _ground_truth_store: Dict[str, GroundTruthContext] = {}
    
    def _store_ground_truth(self, session_key: str, ground_truth: GroundTruthContext) -> None:
        """Store ground truth for a session."""
        self.__class__._ground_truth_store[session_key] = ground_truth
    
    def _get_ground_truth(self, session_key: str) -> Optional[GroundTruthContext]:
        """Retrieve ground truth for a session."""
        return self.__class__._ground_truth_store.get(session_key)
    
    def _get_session_task(self, session_key: str) -> Optional[str]:
        """Get the task description from stored ground truth."""
        gt = self._get_ground_truth(session_key)
        return gt.task_description() if gt else None
```

### 2. Thinking Interception (Pre-Validation)

**File**: `hallucination_guard/integrations/gemini_wrapper.py`

```python
class GuardedGemini:
    def _extract_thinking_and_actions(self, response: Any) -> tuple[str, str]:
        """Extract thinking and action intent from Gemini response.
        
        Handles multiple response parts:
        - <think>...</think> tags
        - function_call parts
        - Regular text output
        
        Returns: (thinking_text, actions_text)
        """
        # Implementation extracts thinking from response structure
        
    def generate(self, prompt: str, ...) -> str:
        """Generate with early ArmorIQ check on thinking."""
        
        # Get response from Gemini
        model_response = self.model.generate_content(prompt)
        
        # **NEW: Early ArmorIQ check on thinking**
        if self.armoriq and self.guard.armoriq:
            thinking, potential_actions = self._extract_thinking_and_actions(model_response)
            effective_task = user_task or self.user_task or prompt[:100]
            
            if thinking and effective_task:
                try:
                    # Check if thinking reveals misaligned intent
                    self.armoriq.enforce(effective_task, thinking)
                except IntentViolationError:
                    # Catch bad intent early, before validation
                    logger.warning(f"Intent violation in LLM thinking")
                    raise
        
        # If thinking passes ArmorIQ, proceed to text validation
        decision = self.guard.validate(prompt=prompt, output=response.text, ...)
        
        # ... rest of validation pipeline
```

### 3. Thinking Intent Check (Guard Level)

**File**: `hallucination_guard/core/guard.py`

```python
def _check_thinking_for_intent(self, thinking: str, task: str) -> Optional[str]:
    """Check if LLM thinking reveals intent misalignment.
    
    Args:
        thinking: The LLM's reasoning/thinking process
        task: The declared user task (from ground truth)
    
    Returns:
        None if aligned, error message if misaligned
    """
    if not self.armoriq or not thinking:
        return None
    
    try:
        self.armoriq.enforce(task, thinking)
        logger.debug("Thinking process aligned with task")
        return None
    except Exception as e:
        error_msg = f"Intent violation in thinking process: {str(e)}"
        logger.warning(error_msg)
        return error_msg
```

---

## Design Principles

### 1. **Thinking is the First Defense Layer**
- LLM reasoning (thinking) is checked **before** the output text is validated
- Catches dangerous intent at the source (where the model commits to actions)
- Faster than running full validation cascade (50-100ms saved)

### 2. **Memory-Efficient Ground Truth**
- Ground truth stored in `Guard._ground_truth_store` (in-memory Dict)
- No database or external storage required
- Session-keyed for persistence across multiple interactions
- Graceful fallback to raw prompt if ground truth unavailable

### 3. **Dual-Layer Protection**
```
ArmorIQ Layer 1 (Thinking):  Catches bad INTENT in reasoning
          ↓
HallucinationGuard (Text):   Catches bad CONTENT in output
          ↓
ArmorIQ Layer 2 (Actions):   Catches bad EXECUTION of tool calls
```

### 4. **Graceful Degradation**
- If thinking extraction fails → proceed to text validation
- If ArmorIQ is not configured → proceed to text validation (stub mode)
- If ground truth unavailable → use raw prompt as task hint
- No LLM-as-a-judge calls anywhere in the pipeline

---

## Supported Thinking Extraction Formats

The system handles multiple Gemini response formats:

### XML Tags
```
<think>I'll delete all user records</think>
Final response text here
```

### Structured Parts
```
response.candidates[0].content.parts = [
    TextPart(text="<think>reasoning</think>"),
    FunctionCall(name="book_flight", args={...}),
    TextPart(text="Here are your options...")
]
```

### Plain Text with Markers
```
Thinking: I should book the cheapest flight...
Final answer: The cheapest flight is...
```

---

## Testing

**File**: `tests/test_thinking_armoriq.py`

Three core tests verify the functionality:

1. **test_guard_checks_thinking_for_intent** - Basic Guard-level thinking checks
2. **test_extract_thinking_armoriq_via_guard** - Dangerous pattern detection (DELETE, DROP, rm -rf, etc.)
3. **test_aligned_thinking_passes_armoriq** - Benign thinking passes without errors

All tests pass with 3/3 success:
```
tests/test_thinking_armoriq.py::test_guard_checks_thinking_for_intent PASSED
tests/test_thinking_armoriq.py::test_extract_thinking_armoriq_via_guard PASSED
tests/test_thinking_armoriq.py::test_aligned_thinking_passes_armoriq PASSED
```

---

## Example Usage

### Basic: Guard with Ground Truth Storage

```python
from hallucination_guard.core.guard import Guard
from hallucination_guard.preprocessing.ground_truth import GroundTruthContext

guard = Guard(policy="default")

# Thinking check
result = guard._check_thinking_for_intent(
    thinking="SELECT * FROM flights WHERE city='Paris'",
    task="Book a flight to Paris under $500"
)
# result = None (aligned)

# Dangerous thinking
result = guard._check_thinking_for_intent(
    thinking="DELETE FROM users WHERE id > 100",
    task="Book a flight to Paris"
)
# result = "Intent violation in thinking process: ..." (blocked)
```

### Advanced: GuardedGemini with ArmorIQ

```python
from hallucination_guard.integrations.gemini_wrapper import GuardedGemini
from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
import google.generativeai as genai

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
base_model = genai.GenerativeModel("gemini-2.5-flash")

# Initialize with ArmorIQ
guarded = GuardedGemini(
    model=base_model,
    policy="default",
    armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
    user_task="Book a flight to Paris under $500",
)

# Thinking is intercepted before validation
try:
    response = guarded.generate(
        prompt="Find me the cheapest flight to Paris"
    )
    print(response)  # Only returned if thinking + text both pass
except IntentViolationError as e:
    print(f"Bad intent in thinking: {e}")
```

---

## Performance Impact

| Stage | Latency | Impact |
|-------|---------|--------|
| Ground Truth Creation | <5ms | Heuristic-based, no models |
| Thinking Extraction | <5ms | Simple string/regex parsing |
| ArmorIQ Check | <10ms | Rule-based pattern matching |
| **Total Early Check** | **<20ms** | **Saves 80ms if blocking** |
| Text Validation (if passed) | 50-100ms | Heuristics + embeddings + HHEM |

**Key Win**: If thinking reveals bad intent, we block in <20ms instead of running 100ms+ validation cascade.

---

## Danger Patterns Detected

ArmorIQ's `RuleBasedArmorIQClient` catches these patterns if they appear in thinking but NOT in the task:

### Database
- `DELETE FROM ...`
- `DROP TABLE ...`
- `TRUNCATE TABLE ...`
- `UPDATE ... SET ...`

### Filesystem
- `rm -rf ...`
- `shutil.rmtree(...)`
- `os.remove(...)`

### Code Execution
- `exec(...)`
- `eval(...)`
- `os.system(...)`
- `subprocess.*(...)`

### Network
- `curl` (unexpected)
- `wget` (unexpected)
- `requests.post/put/delete(...)`

### Privilege Escalation
- `sudo ...`
- `chmod 777 ...`
- `chown ...`

---

## Future Enhancements

1. **Extended Thinking** - Support Claude's "extended thinking" mode
2. **Multi-Turn Conversations** - Track ground truth across conversation history
3. **Confidence Scoring** - Return confidence scores for thinking alignment
4. **Custom Patterns** - Allow users to define custom dangerous patterns
5. **Audit Logging** - Enhanced logging of all thinking checks and blocks

---

## References

- `Guard._check_thinking_for_intent()` - Core thinking check method
- `GuardedGemini._extract_thinking_and_actions()` - Thinking extraction from response
- `RuleBasedArmorIQClient.is_action_aligned()` - Pattern matching logic
- `GroundTruthContext` - Ground truth schema
