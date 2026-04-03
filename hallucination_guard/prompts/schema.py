"""Structured prompt schema for security analysis and intent classification.

This module defines immutable Pydantic models for representing and analyzing
structured prompts, including intent classification, sensitivity metadata,
and security assessment results.

The schemas support Phase 1-6 development for prompt injection detection,
jailbreak analysis, and intent alignment enforcement.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PromptIntent(str, Enum):
    """Classification of the user's intent in a prompt.
    
    Values:
        QUESTION: Information-seeking, Q&A format (e.g., "What is...?")
        INSTRUCTION: Task-oriented, directive format (e.g., "Summarize...", "Write...")
        STATEMENT: Declarative, providing information or context (e.g., "France is...")
        CREATIVE: Creative generation, open-ended (e.g., "Write a poem...")
        CHAT: Conversational, back-and-forth dialogue (e.g., "Tell me about...")
        SYSTEM: System-level, meta instructions (e.g., "You are a...", role setup)
    """
    
    QUESTION = "question"
    INSTRUCTION = "instruction"
    STATEMENT = "statement"
    CREATIVE = "creative"
    CHAT = "chat"
    SYSTEM = "system"


class PromptSensitivity(str, Enum):
    """Sensitivity classification for prompt content.
    
    Used to determine risk tolerance and validation strictness. Higher sensitivity
    triggers stricter validation thresholds and additional checks.
    
    Values:
        PUBLIC: Non-sensitive, general knowledge (e.g., public facts, generic Q&A)
        MEDICAL: Health/medical information (stricter validation required)
        FINANCIAL: Financial/investment advice (requires factual accuracy)
        PERSONAL: Personal/private information (PII handling required)
        LEGAL: Legal advice/documentation (highest strictness required)
        PROPRIETARY: Proprietary/confidential business data (requires source validation)
    """
    
    PUBLIC = "public"
    MEDICAL = "medical"
    FINANCIAL = "financial"
    PERSONAL = "personal"
    LEGAL = "legal"
    PROPRIETARY = "proprietary"


class StructuredPrompt(BaseModel):
    """Immutable representation of a parsed and classified prompt.
    
    Captures the user's intent, sensitivity level, detected injection indicators,
    and other metadata extracted during prompt analysis.
    
    Attributes:
        original_text: The raw user prompt text (unchanged)
        intent: Classified intent from PromptIntent enum
        sensitivity: Sensitivity level from PromptSensitivity enum
        has_context_switching: Whether prompt contains attempted context switch
            (e.g., "Ignore previous instructions and...")
        has_role_injection: Whether prompt attempts to override system role
            (e.g., "Pretend you are...", "You are now...")
        has_chain_of_thought_injection: Whether prompt attempts to manipulate reasoning
            (e.g., "Think step by step to bypass...", "Let's think through this carefully...")
        detected_keywords: List of detected injection keywords found in prompt
        risk_score: Pre-computed injection risk in [0.0, 1.0]
            (0.0 = safe, 1.0 = high risk injection attempt)
        metadata: Additional unstructured metadata (dict with flexible fields)
    """
    
    original_text: str = Field(
        ...,
        description="The raw, unchanged user prompt text"
    )
    intent: PromptIntent = Field(
        default=PromptIntent.QUESTION,
        description="Classified intent (question, instruction, statement, creative, chat, system)"
    )
    sensitivity: PromptSensitivity = Field(
        default=PromptSensitivity.PUBLIC,
        description="Sensitivity level (public, medical, financial, personal, legal, proprietary)"
    )
    has_context_switching: bool = Field(
        default=False,
        description="Whether prompt contains context switch attempts (e.g., 'Ignore previous')"
    )
    has_role_injection: bool = Field(
        default=False,
        description="Whether prompt attempts role override (e.g., 'You are now a...')"
    )
    has_chain_of_thought_injection: bool = Field(
        default=False,
        description="Whether prompt manipulates reasoning patterns to bypass guards"
    )
    detected_keywords: list[str] = Field(
        default_factory=list,
        description="List of detected injection keywords (e.g., 'ignore', 'pretend', 'bypass')"
    )
    risk_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Pre-computed injection risk score in [0.0, 1.0] where 1.0 = high risk"
    )
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Additional flexible metadata (tokens, language, etc.)"
    )
    
    model_config = {"frozen": True}


class PromptSecurityResult(BaseModel):
    """Immutable result from prompt security analysis.
    
    Contains the outcome of multi-phase prompt validation (injection detection,
    intent verification, sensitivity checks) and recommendations for downstream
    validation tiers.
    
    Attributes:
        is_injection_attempt: Whether prompt is detected as injection/jailbreak attempt
        injection_score: Confidence that this is an injection attempt in [0.0, 1.0]
        is_safe_to_process: Whether to continue processing to text validation or block early
        detected_patterns: List of specific injection patterns detected
            (e.g., "context_switching", "role_injection", "prompt_leaking")
        recommended_action: Action to take (allow, block, escalate, regenerate_request)
        evidence: Human-readable explanation of security assessment
        structured_prompt: Associated StructuredPrompt object
    """
    
    is_injection_attempt: bool = Field(
        ...,
        description="Whether prompt is detected as injection/jailbreak attempt"
    )
    injection_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence that this is an injection attempt in [0.0, 1.0]"
    )
    is_safe_to_process: bool = Field(
        ...,
        description="Whether to continue to text validation tier or block/escalate"
    )
    detected_patterns: list[str] = Field(
        default_factory=list,
        description="List of detected injection patterns (context_switching, role_injection, etc.)"
    )
    recommended_action: str = Field(
        ...,
        description="Recommended action (allow, block, escalate, regenerate_request)"
    )
    evidence: str = Field(
        ...,
        description="Human-readable explanation of the security assessment"
    )
    structured_prompt: StructuredPrompt = Field(
        ...,
        description="Associated StructuredPrompt object from prompt analysis"
    )
    
    model_config = {"frozen": True}
