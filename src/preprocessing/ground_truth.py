from pydantic import BaseModel, Field
from verdict.prompts.schema import PromptIntent

class GroundTruthContext(BaseModel):
    """Structured ground truth extracted from prompt analysis.

    Represents the canonical understanding of user intent and context that
    should be used consistently throughout a session for validation and
    action enforcement.

    Attributes:
        original_prompt: The raw user prompt that was analyzed.
        intent: Classified intent (question, instruction, creative, etc.).
        core_task: Extracted core task description (e.g., "search for flights").
        constraints: List of constraints or requirements identified.
        entities: Key entities mentioned (people, places, concepts).
        domain: Inferred domain (healthcare, finance, general, etc.).
        sensitivity_tags: Security/privacy sensitivity flags.
        context_requirements: What context/reference material is needed.
        created_at: When this ground truth was established.
        confidence: Confidence in the analysis (0.0 to 1.0).
    """

    original_prompt: str
    intent: PromptIntent
    core_task: str
    constraints: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    domain: str = "general"
    sensitivity_tags: list[str] = Field(default_factory=list)
    context_requirements: list[str] = Field(default_factory=list)
    created_at: float
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)

    model_config = {"frozen": True}

    def get_task_description(self) -> str:
        """Get a concise task description for ArmorIQ enforcement."""
        return self.core_task or self.original_prompt

    def get_context_hints(self) -> list[str]:
        """Get hints about what context should be available."""
        return self.context_requirements.copy()

    def is_sensitive_domain(self) -> bool:
        """Check if this involves sensitive domains."""
        sensitive_domains = {"healthcare", "medical", "finance", "financial",
                           "legal", "government", "personal", "private"}
        return any(tag in sensitive_domains for tag in [self.domain] + self.sensitivity_tags)