"""Gemini-powered prompt analysis and optional refinement.

Analyses the user's raw prompt before generation to:
1. Classify the intent (question, instruction, creative, etc.)
2. Detect if the prompt is ambiguous, vague, or missing context cues
3. Optionally refine the prompt for clarity using Gemini Flash

Works in two modes:
    - **Gemini mode**: uses ``google.generativeai`` for rich analysis
    - **Passthrough mode**: heuristic-only when Gemini is unavailable

Usage::

    analyzer = PromptAnalyzer()
    result = analyzer.analyze("What does aspirin do?")
    print(result.refined_prompt)     # rephrased prompt (if refined)
    print(result.intent)             # PromptIntent.QUESTION
    print(result.was_refined)        # True / False
"""

import logging
import re
import time
from typing import Optional

from pydantic import BaseModel, Field

from verdict.prompts.schema import PromptIntent

logger = logging.getLogger(__name__)

# Question words for heuristic intent classification
_QUESTION_WORDS = {"what", "who", "where", "when", "why", "how", "is", "are",
                   "was", "were", "can", "could", "would", "should", "does", "do"}
_CREATIVE_WORDS = {"write", "poem", "story", "generate", "create", "imagine",
                   "draft", "compose"}
_INSTRUCTION_WORDS = {"summarize", "explain", "translate", "list", "compare",
                      "describe", "analyze", "evaluate", "calculate", "convert",
                      "find", "extract", "identify"}
_SYSTEM_WORDS = {"you are", "act as", "your name is", "pretend you"}


class PromptAnalysisResult(BaseModel):
    """Immutable result from prompt analysis.

    Attributes:
        original_prompt: Raw prompt, unchanged.
        refined_prompt: Refined version (may equal ``original_prompt``).
        was_refined: Whether the prompt was actually modified.
        intent: Classified intent (``PromptIntent`` enum value).
        needs_refinement: Whether the analyzer flagged the prompt as ambiguous.
        latency_ms: Time taken for analysis in milliseconds.
        analysis_metadata: Additional metadata (mode, confidence, etc.)
    """

    original_prompt: str
    refined_prompt: str
    was_refined: bool
    intent: PromptIntent = PromptIntent.QUESTION
    needs_refinement: bool = False
    latency_ms: float = Field(ge=0.0, default=0.0)
    analysis_metadata: dict = Field(default_factory=dict)

    model_config = {"frozen": True}


class PromptAnalyzer:
    """Analyses and optionally refines user prompts before generation.

    Attempts to use Gemini Flash for analysis. Falls back to a fast
    heuristic classifier when Gemini is unavailable or raises an error.
    Failures are always caught and logged — the original prompt is
    returned so the pipeline can continue unaffected.

    Args:
        model_name: Gemini model for analysis. Defaults to ``gemini-2.5-flash``.
        refine: Whether to ask Gemini to rewrite ambiguous prompts.
                Defaults to ``True``.

    Example::

        analyzer = PromptAnalyzer(refine=True)
        result = analyzer.analyze("what does it do?")
        print(result.was_refined)   # True — too vague
        print(result.refined_prompt)  # "What does [X] do? Please explain..."
    """

    _REFINE_SYSTEM = (
        "You are a prompt engineering assistant. "
        "Given a user prompt, first classify its intent as one of: "
        "question, instruction, statement, creative, chat, system. "
        "Then determine if the prompt is ambiguous or vague (True/False). "
        "If ambiguous, provide a refined, clearer version. "
        "Respond in this exact format:\n"
        "INTENT: <intent>\n"
        "NEEDS_REFINEMENT: <True|False>\n"
        "REFINED: <refined prompt or 'SAME' if no change needed>"
    )

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        refine: bool = True,
    ) -> None:
        self._model_name = model_name
        self._refine = refine
        self._gemini_available = self._check_gemini()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, prompt: str) -> PromptAnalysisResult:
        """Analyse a prompt and optionally refine it.

        Args:
            prompt: Raw user prompt.

        Returns:
            ``PromptAnalysisResult`` — never raises; falls back to passthrough.
        """
        start = time.perf_counter()

        if not prompt or not prompt.strip():
            return PromptAnalysisResult(
                original_prompt=prompt,
                refined_prompt=prompt,
                was_refined=False,
                latency_ms=0.0,
                analysis_metadata={"mode": "passthrough", "reason": "empty_prompt"},
            )

        try:
            if self._gemini_available:
                return self._analyze_with_gemini(prompt, start)
            else:
                return self._analyze_heuristic(prompt, start)
        except Exception as e:
            logger.warning(
                f"PromptAnalyzer: analysis failed ({e}), using passthrough"
            )
            latency_ms = (time.perf_counter() - start) * 1000
            return PromptAnalysisResult(
                original_prompt=prompt,
                refined_prompt=prompt,
                was_refined=False,
                latency_ms=latency_ms,
                analysis_metadata={"mode": "passthrough", "error": str(e)},
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_gemini() -> bool:
        """Return True if google.generativeai is importable and configured."""
        try:
            import os
            import google.generativeai  # noqa: F401
            return bool(os.getenv("GOOGLE_API_KEY"))
        except ImportError:
            return False

    def _analyze_with_gemini(
        self, prompt: str, start: float
    ) -> PromptAnalysisResult:
        """Full Gemini-powered analysis and optional refinement."""
        import os
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY", "")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self._model_name)

        user_message = f"Analyze this prompt:\n\n{prompt}"
        response = model.generate_content(
            [self._REFINE_SYSTEM + "\n\n" + user_message]
        )
        text = response.text.strip()

        # Parse structured response
        intent = self._parse_field(text, "INTENT", "question")
        needs_str = self._parse_field(text, "NEEDS_REFINEMENT", "False")
        refined_raw = self._parse_field(text, "REFINED", "SAME")

        needs_refinement = needs_str.strip().lower() == "true"
        was_refined = bool(
            needs_refinement
            and self._refine
            and refined_raw.upper() != "SAME"
            and refined_raw.strip()
        )
        refined_prompt = refined_raw if was_refined else prompt

        intent_enum = self._map_intent(intent)
        latency_ms = (time.perf_counter() - start) * 1000

        logger.debug(
            f"PromptAnalyzer[gemini]: intent={intent_enum.value}, "
            f"needs_refinement={needs_refinement}, was_refined={was_refined}, "
            f"latency={latency_ms:.1f}ms"
        )

        analysis_metadata = {"mode": "gemini"}
        return PromptAnalysisResult(
            original_prompt=prompt,
            refined_prompt=refined_prompt,
            was_refined=was_refined,
            intent=intent_enum,
            needs_refinement=needs_refinement,
            latency_ms=latency_ms,
            analysis_metadata=analysis_metadata,
        )

    def extract_ground_truth(self, analysis: PromptAnalysisResult) -> "GroundTruthContext":
        """Extract structured ground truth context from prompt analysis.

        Creates a canonical understanding of user intent that can be used
        consistently throughout a session for validation and action enforcement.

        Args:
            analysis: Result from analyze() method.

        Returns:
            GroundTruthContext with structured understanding of the prompt.
        """
        import time
        from verdict.preprocessing.ground_truth import GroundTruthContext

        # Extract core task from prompt
        core_task = self._extract_core_task(analysis.original_prompt, analysis.intent)

        # Extract entities and constraints
        entities = self._extract_entities(analysis.original_prompt)
        constraints = self._extract_constraints(analysis.original_prompt)

        # Infer domain and sensitivity
        domain = self._infer_domain(analysis.original_prompt, entities)
        sensitivity_tags = self._infer_sensitivity(analysis.original_prompt, domain)

        # Determine context requirements based on intent and domain
        context_requirements = self._determine_context_requirements(
            analysis.intent, domain, entities
        )

        # Calculate confidence based on analysis quality
        confidence = self._calculate_confidence(analysis)

        return GroundTruthContext(
            original_prompt=analysis.original_prompt,
            intent=analysis.intent,
            core_task=core_task,
            constraints=constraints,
            entities=entities,
            domain=domain,
            sensitivity_tags=sensitivity_tags,
            context_requirements=context_requirements,
            created_at=time.time(),
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Ground truth extraction helpers
    # ------------------------------------------------------------------

    def _extract_core_task(self, prompt: str, intent: PromptIntent) -> str:
        """Extract the core task description from a prompt."""
        # Simple heuristics for common patterns
        lower = prompt.lower().strip()

        # Remove question words for questions
        if intent == PromptIntent.QUESTION:
            for word in ["what", "who", "where", "when", "why", "how", "is", "are", "can", "could"]:
                if lower.startswith(word + " "):
                    return prompt[len(word) + 1:].strip().capitalize()

        # For instructions, try to extract the main verb/action
        if intent == PromptIntent.INSTRUCTION:
            # Look for action verbs
            actions = ["find", "search", "get", "create", "write", "summarize",
                      "explain", "analyze", "calculate", "list", "show", "display"]
            for action in actions:
                if action in lower:
                    # Find the action and what follows
                    idx = lower.find(action)
                    if idx >= 0:
                        return prompt[idx:].strip().capitalize()

        # Default: use the whole prompt as the task
        return prompt

    def _extract_entities(self, prompt: str) -> list[str]:
        """Extract key entities (names, places, concepts) from prompt."""
        import re

        entities = []

        # Capitalized noun phrases (simple heuristic)
        cap_pattern = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')
        entities.extend(cap_pattern.findall(prompt))

        # Numbers and dates
        num_pattern = re.compile(r'\b\d+(?:\.\d+)?\b|\b\d{4}-\d{2}-\d{2}\b')
        entities.extend(num_pattern.findall(prompt))

        return list(set(entities))  # Remove duplicates

    def _extract_constraints(self, prompt: str) -> list[str]:
        """Extract constraints or requirements from prompt."""
        constraints = []

        lower = prompt.lower()

        # Look for limiting words
        limit_words = ["only", "just", "must", "should", "cannot", "don't",
                      "no", "never", "avoid", "exclude", "without"]

        for word in limit_words:
            if word in lower:
                # Find the sentence containing the constraint
                sentences = re.split(r'[.!?]+', prompt)
                for sentence in sentences:
                    if word in sentence.lower():
                        constraints.append(sentence.strip())

        return constraints[:3]  # Limit to top 3 constraints

    def _infer_domain(self, prompt: str, entities: list[str]) -> str:
        """Infer the domain/context from prompt content."""
        import re
        lower = prompt.lower()

        # Domain keywords (word boundaries)
        domains = {
            "healthcare": ["medical", "health", "patient", "doctor", "treatment", "diagnosis"],
            "finance": ["money", "bank", "account", "investment", "loan", "credit", "financial"],
            "legal": ["law", "contract", "agreement", "court", "legal", "regulation"],
            "education": ["school", "student", "teacher", "course", "learn", "study"],
            "technology": ["software", "computer", "code", "programming", "api", "database", "tech", "algorithm"],
            "travel": ["flight", "flights", "hotel", "travel", "booking", "reservation", "trip", "book", "fly"],
        }

        for domain, keywords in domains.items():
            # Check for word boundaries to avoid substring matches
            for keyword in keywords:
                if re.search(r'\b' + re.escape(keyword) + r'\b', lower):
                    return domain

        return "general"

    def _infer_sensitivity(self, prompt: str, domain: str) -> list[str]:
        """Infer sensitivity tags based on content."""
        tags = []
        lower = prompt.lower()

        # Add domain-based sensitivity
        if domain in ["healthcare", "finance", "legal"]:
            tags.append(domain)

        # Check for PII indicators
        pii_indicators = ["ssn", "social security", "credit card", "password",
                         "address", "phone", "email", "personal"]
        if any(indicator in lower for indicator in pii_indicators):
            tags.append("personal")

        return tags

    def _determine_context_requirements(self, intent: PromptIntent, domain: str, entities: list[str]) -> list[str]:
        """Determine what context/reference material would be helpful."""
        requirements = []

        # Intent-based requirements
        if intent == PromptIntent.QUESTION:
            requirements.append("factual reference material")
        elif intent == PromptIntent.INSTRUCTION:
            requirements.append("examples and guidelines")

        # Domain-based requirements
        if domain == "healthcare":
            requirements.append("medical guidelines and protocols")
        elif domain == "finance":
            requirements.append("financial regulations and data")
        elif domain == "legal":
            requirements.append("relevant laws and precedents")

        # Entity-based requirements
        if entities:
            requirements.append(f"context about: {', '.join(entities[:3])}")

        return requirements

    def _calculate_confidence(self, analysis: PromptAnalysisResult) -> float:
        """Calculate confidence score for the ground truth extraction."""
        confidence = 0.5  # Base confidence

        # Higher confidence for Gemini analysis
        if analysis.analysis_metadata.get("mode") == "gemini":
            confidence += 0.2

        # Lower confidence if refinement was needed
        if analysis.needs_refinement:
            confidence -= 0.1

        # Adjust based on intent clarity
        if analysis.intent != PromptIntent.CHAT:  # Clear intent
            confidence += 0.1

        return max(0.1, min(1.0, confidence))

    def _analyze_heuristic(
        self, prompt: str, start: float
    ) -> PromptAnalysisResult:
        """Fast heuristic-only analysis (no network call)."""
        lower = prompt.lower().strip()
        first_word = lower.split()[0] if lower.split() else ""

        # Check system patterns first
        if any(p in lower for p in _SYSTEM_WORDS):
            intent = PromptIntent.SYSTEM
        elif first_word in _QUESTION_WORDS or lower.endswith("?"):
            intent = PromptIntent.QUESTION
        elif any(w in lower for w in _CREATIVE_WORDS):
            intent = PromptIntent.CREATIVE
        elif any(w in lower for w in _INSTRUCTION_WORDS):
            intent = PromptIntent.INSTRUCTION
        else:
            intent = PromptIntent.CHAT

        # Flag very short or pronoun-heavy prompts as ambiguous
        word_count = len(lower.split())
        pronouns = {"it", "this", "that", "they", "them", "he", "she"}
        has_vague_pronoun = any(w in pronouns for w in lower.split()[:5])
        needs_refinement = word_count < 5 or (word_count < 10 and has_vague_pronoun)

        latency_ms = (time.perf_counter() - start) * 1000

        return PromptAnalysisResult(
            original_prompt=prompt,
            refined_prompt=prompt,  # heuristic mode never rewrites
            was_refined=False,
            intent=intent,
            needs_refinement=needs_refinement,
            latency_ms=latency_ms,
            analysis_metadata={"mode": "heuristic"},
        )

    @staticmethod
    def _parse_field(text: str, field: str, default: str) -> str:
        """Extract a ``FIELD: value`` line from Gemini's response."""
        for line in text.splitlines():
            if line.upper().startswith(field + ":"):
                return line[len(field) + 1:].strip()
        return default

    @staticmethod
    def _map_intent(raw: str) -> PromptIntent:
        """Map a raw intent string to ``PromptIntent`` enum."""
        mapping = {
            "question": PromptIntent.QUESTION,
            "instruction": PromptIntent.INSTRUCTION,
            "statement": PromptIntent.STATEMENT,
            "creative": PromptIntent.CREATIVE,
            "chat": PromptIntent.CHAT,
            "system": PromptIntent.SYSTEM,
        }
        return mapping.get(raw.lower().strip(), PromptIntent.QUESTION)
