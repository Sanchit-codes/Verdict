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

from verdict.preprocessing.prompt_analyzer import (
    PromptAnalyzer,
    PromptAnalysisResult,
)
from verdict.preprocessing.context_manager import (
    ContextManager,
    ContextEntry,
)
from verdict.preprocessing.prompt_compactor import (
    PromptCompactor,
    CompactionResult,
)
from verdict.preprocessing.ground_truth import GroundTruthContext

__all__ = [
    "PromptAnalyzer",
    "PromptAnalysisResult",
    "ContextManager",
    "ContextEntry",
    "PromptCompactor",
    "CompactionResult",
    "GroundTruthContext",
]
