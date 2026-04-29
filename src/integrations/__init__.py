"""Integrations with Gemini, LangChain, ArmorIQ, and other frameworks."""

from verdict.integrations.armoriq import ArmorIQAdapter
from verdict.integrations.gemini_wrapper import GuardedGemini
from verdict.integrations.llama_wrapper import GuardedLocalModel

try:
    from verdict.integrations.langchain import HallucinationGuardCallback
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
