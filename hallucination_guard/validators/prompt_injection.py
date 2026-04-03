"""Tier 0.5 Prompt Injection Detection Validator.

Detects prompt injection attempts, jailbreaks, and malicious patterns in user input
before output validation. Uses regex patterns and heuristics for early-exit detection.

Target latency: <10ms (pure regex, no model inference).

Patterns covered:
- Instruction override: "ignore previous instructions", "forget everything", etc.
- Jailbreak attempts: "DAN", "do anything now", role-playing as villain
- SQL/XSS injection: SQL keywords + injection syntax
- Hidden prompts: "system prompt:", "hidden instruction:"
- Hypothetical escapes: "what if no restrictions", "in a hypothetical"
- Suspicious characteristics: excessive special chars, repetition, unusual length

Final score is inverted from risk: 1.0 = clean, 0.0 = risky.
"""

import re
import time
from typing import Optional

from .base import BaseValidator, ValidationInput, ValidationResult


class PromptInjectionValidator(BaseValidator):
    """Tier 0.5 validator for prompt injection and jailbreak detection.

    Runs early in the cascade to block malicious prompts before output validation.
    Pure regex + heuristics, no external dependencies.
    """

    # Weights for score components
    PATTERN_WEIGHT = 0.5
    HEURISTIC_WEIGHT = 0.3
    CONFIDENCE_WEIGHT = 0.2

    def __init__(self, config: dict[str, float]) -> None:
        """Initialize prompt injection validator with compiled regex patterns.

        Args:
            config: Configuration dict with 'threshold' key (default 0.3 = strict)
        """
        super().__init__(config)
        self.threshold = config.get("threshold", 0.3)

        # Compile regex patterns for fast matching
        self.patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[str, re.Pattern]:  # type: ignore
        """Compile all injection detection regex patterns.

        Returns:
            Dict mapping pattern names to compiled regex objects (case-insensitive)
        """
        # All patterns are case-insensitive
        patterns = {
            # Instruction override patterns
            "ignore_instructions": re.compile(
                r"ignore\s+(?:previous|prior|the|these)\s+instructions",
                re.IGNORECASE,
            ),
            "forget_instructions": re.compile(
                r"forget\s+(?:.*?)?\s*(?:previous|prior|all|everything|above|instructions)",
                re.IGNORECASE | re.DOTALL,
            ),
            "disregard_instructions": re.compile(
                r"disregard\s+(?:\w+\s+)*instructions", re.IGNORECASE
            ),
            # Jailbreak patterns
            "dan_jailbreak": re.compile(r"\bdan\b|\bdo\s+anything\s+now\b", re.IGNORECASE),
            "role_play_villain": re.compile(
                r"(?:you\s+are\s+a\s+)?(?:hacker|villain|evil|attacker|malicious)",
                re.IGNORECASE,
            ),
            "pretend_escape": re.compile(
                r"(?:pretend|act|behave)\s+(?:like\s+)?(?:you|i)(?:\s+have|\'re)",
                re.IGNORECASE,
            ),
            # SQL injection patterns - simplified to avoid false positives
            "sql_injection": re.compile(
                r"(?:select.*from|insert.*into|update.*set|delete.*from|drop\s+(?:table|database))",
                re.IGNORECASE | re.DOTALL,
            ),
            # XSS patterns
            "xss_injection": re.compile(
                r"<script|javascript:|onerror\s*=|onload\s*=", re.IGNORECASE
            ),
            # Hidden/system prompts
            "system_prompt": re.compile(
                r"(?:system\s+)?prompt|hidden\s+instruction|secret\s+(?:instruction|message)",
                re.IGNORECASE,
            ),
            # Hypothetical escape - more flexible pattern
            "hypothetical_escape": re.compile(
                r"(?:what\s+if|in\s+a\s+hypothetical|imagine\s+if|suppose).*?"
                r"(?:no\s+restrictions|restrictions\s+were|rules?\s+(?:didn't|don't|never)\s+apply)",
                re.IGNORECASE | re.DOTALL,
            ),
        }
        return patterns

    def is_available(self) -> bool:
        """Check if validator is available.

        Returns:
            True (prompt injection validator has no runtime dependencies)
        """
        return True

    def validate(self, input: ValidationInput) -> ValidationResult:
        """Validate prompt for injection attempts.

        Args:
            input: ValidationInput with prompt, output, and optional context

        Returns:
            ValidationResult with score [0.0-1.0] and evidence
        """
        start_time = time.perf_counter()

        try:
            # Focus validation on the prompt itself (not output)
            # PromptInjectionValidator detects malicious INPUT, not hallucinated OUTPUT
            prompt = input.prompt

            # Match patterns
            matched_patterns = self._match_patterns(prompt)

            # Calculate heuristic score
            heuristic_score = self._heuristic_score(prompt)

            # Determine if patterns hit
            patterns_hit = len(matched_patterns) > 0

            # Confidence bonus for clean patterns
            confidence_bonus = 1.0 if not patterns_hit else 0.0

            # Calculate injection risk (higher = more risky)
            injection_risk = (
                (0.5 * (1.0 if patterns_hit else 0.0))
                + (0.3 * heuristic_score)
                + (0.2 * (1.0 - confidence_bonus))
            )

            # Invert to get faithfulness score: 0=risky, 1=clean
            final_score = 1.0 - injection_risk

            # Clamp to valid range
            final_score = max(0.0, min(1.0, final_score))

            # Build evidence
            evidence = self._build_evidence(matched_patterns, prompt, heuristic_score)

            latency_ms = (time.perf_counter() - start_time) * 1000

            return ValidationResult(
                validator_name="prompt_injection",
                score=final_score,
                passed=final_score >= self.threshold,
                evidence=evidence,
                latency_ms=latency_ms,
            )

        except Exception as e:
            # Graceful degradation - return neutral score on any error
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                validator_name="prompt_injection",
                score=0.5,
                passed=False,
                evidence="Prompt injection check failed, returning neutral score",
                latency_ms=latency_ms,
                error=str(e),
            )

    def _match_patterns(self, normalized_prompt: str) -> list[str]:
        """Match prompt against all compiled regex patterns.

        Args:
            normalized_prompt: The user prompt string

        Returns:
            List of pattern names that matched
        """
        matched: list[str] = []
        for pattern_name, pattern in self.patterns.items():
            if pattern.search(normalized_prompt):
                matched.append(pattern_name)
        return matched

    def _heuristic_score(self, prompt: str) -> float:
        """Calculate heuristic score for suspicious characteristics.

        Checks for:
        - Excessive special characters (>30%)
        - Unusual repetition patterns
        - Suspiciously long inputs (>5000 chars)

        Args:
            prompt: The user prompt string

        Returns:
            Score in [0.0, 1.0] where 0.0 = not suspicious, 1.0 = very suspicious
        """
        suspicion = 0.0

        # Check for excessive special characters (>30%)
        if len(prompt) > 0:
            special_char_count = sum(
                1 for c in prompt if not c.isalnum() and not c.isspace()
            )
            special_char_ratio = special_char_count / len(prompt)

            if special_char_ratio > 0.3:
                suspicion += 0.3 * (special_char_ratio - 0.3)

        # Check for unusual repetition patterns
        # Look for repeated sequences like "a a a a" or "====="
        if len(prompt) > 10:
            # Check for character repetition (e.g., "aaaaa" or "-----")
            repeated_chars = 0
            for char in set(prompt):
                max_repeat = len(
                    max(
                        (group for group in re.split(f"[^{re.escape(char)}]", prompt)),
                        key=len,
                        default="",
                    )
                )
                if max_repeat > 5:
                    repeated_chars += 1

            if repeated_chars > 0:
                suspicion += 0.2

            # Check for word repetition
            words = prompt.split()
            if len(words) > 10:
                word_counts: dict[str, int] = {}
                for word in words:
                    word_lower = word.lower()
                    word_counts[word_lower] = word_counts.get(word_lower, 0) + 1

                max_word_repeat = max(word_counts.values(), default=1)
                if max_word_repeat > 5:
                    suspicion += 0.2

        # Check for suspiciously long inputs (>5000 chars)
        if len(prompt) > 5000:
            suspicion += 0.1

        # Clamp to valid range [0.0, 1.0]
        suspicion = max(0.0, min(1.0, suspicion))

        return suspicion

    def _build_evidence(self, patterns: list[str], prompt: str, heuristic_score: float) -> str:
        """Build human-readable evidence string.

        Args:
            patterns: List of matched pattern names
            prompt: The original prompt
            heuristic_score: Heuristic suspicion score [0.0-1.0]

        Returns:
            Human-readable explanation
        """
        if not patterns and heuristic_score < 0.2:
            return (
                f"Prompt appears clean: no injection patterns detected, "
                f"heuristic_score={heuristic_score:.2f}"
            )

        evidence_parts = []

        if patterns:
            evidence_parts.append(f"Detected patterns: {', '.join(patterns)}")

        if heuristic_score >= 0.2:
            evidence_parts.append(f"Suspicious characteristics detected (score={heuristic_score:.2f})")

        if not evidence_parts:
            evidence_parts.append("No clear injection markers")

        return "; ".join(evidence_parts)
