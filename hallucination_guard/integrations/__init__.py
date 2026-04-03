"""Integrations with Gemini, LangChain, ArmorIQ, and other frameworks."""

from hallucination_guard.integrations.armoriq import ArmorIQAdapter
from hallucination_guard.integrations.gemini_wrapper import GuardedGemini
from hallucination_guard.integrations.llama_wrapper import GuardedLocalModel

try:
    from hallucination_guard.integrations.langchain import HallucinationGuardCallback
    __all__ = [
        "GuardedGemini",
        "GuardedLocalModel",
        "ArmorIQAdapter",
        "HallucinationGuardCallback",
    ]
except ImportError:
    __all__ = [
        "GuardedGemini",
        "GuardedLocalModel",
        "ArmorIQAdapter",
    ]
