"""Preprocessing module for HallucinationGuard.

Provides prompt analysis, context management, and context compaction
as a pre-generation step before the validation pipeline runs.

Exports:
    PromptAnalyzer: Gemini-powered prompt analysis & refinement
    ContextManager: In-memory context store with dynamic updates
    PromptCompactor: Extractive context compaction
    PromptAnalysisResult: Result schema from prompt analysis
    CompactionResult: Result schema from context compaction
"""

from hallucination_guard.preprocessing.prompt_analyzer import (
    PromptAnalyzer,
    PromptAnalysisResult,
)
from hallucination_guard.preprocessing.context_manager import (
    ContextManager,
    ContextEntry,
)
from hallucination_guard.preprocessing.prompt_compactor import (
    PromptCompactor,
    CompactionResult,
)

__all__ = [
    "PromptAnalyzer",
    "PromptAnalysisResult",
    "ContextManager",
    "ContextEntry",
    "PromptCompactor",
    "CompactionResult",
]
