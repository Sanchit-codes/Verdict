"""Structured prompt schema and security analysis module.

Exports the public API for prompt classification, intent detection,
and injection/jailbreak analysis.
"""

from hallucination_guard.prompts.schema import (
    PromptIntent,
    PromptSecurityResult,
    PromptSensitivity,
    StructuredPrompt,
)

__all__ = [
    "PromptIntent",
    "PromptSensitivity",
    "StructuredPrompt",
    "PromptSecurityResult",
]
