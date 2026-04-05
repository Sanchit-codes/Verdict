"""Test ground truth extraction and context management."""

import pytest
from hallucination_guard.preprocessing.prompt_analyzer import PromptAnalyzer, PromptAnalysisResult
from hallucination_guard.preprocessing.context_manager import ContextManager
from hallucination_guard.preprocessing.ground_truth import GroundTruthContext
from hallucination_guard.prompts.schema import PromptIntent


def test_ground_truth_extraction():
    """Test that ground truth context is properly extracted from prompt analysis."""
    analyzer = PromptAnalyzer()

    # Test a question prompt
    analysis = PromptAnalysisResult(
        original_prompt="What is the capital of France?",
        refined_prompt="What is the capital of France?",
        was_refined=False,
        intent=PromptIntent.QUESTION,
        needs_refinement=False,
        latency_ms=10.0,
        analysis_metadata={"mode": "heuristic"}
    )

    ground_truth = analyzer.extract_ground_truth(analysis)

    assert isinstance(ground_truth, GroundTruthContext)
    assert ground_truth.original_prompt == "What is the capital of France?"
    assert ground_truth.intent == PromptIntent.QUESTION
    assert ground_truth.core_task == "Is the capital of france?"  # Question word removed, capitalized
    assert ground_truth.domain == "general"
    assert ground_truth.confidence >= 0.1


def test_ground_truth_storage_and_retrieval():
    """Test that ground truth context can be stored and retrieved from ContextManager."""
    mgr = ContextManager()
    analyzer = PromptAnalyzer()

    # Create and store ground truth
    analysis = PromptAnalysisResult(
        original_prompt="Find me flights to Paris",
        refined_prompt="Find me flights to Paris",
        was_refined=False,
        intent=PromptIntent.INSTRUCTION,
        needs_refinement=False,
        latency_ms=15.0,
        analysis_metadata={"mode": "heuristic"}
    )

    ground_truth = analyzer.extract_ground_truth(analysis)
    mgr.store_ground_truth("travel_session", ground_truth)

    # Retrieve and verify
    retrieved = mgr.retrieve_ground_truth("travel_session")
    assert retrieved is not None
    assert retrieved.core_task == "Find me flights to paris"
    assert retrieved.domain == "travel"
    assert retrieved.intent == PromptIntent.INSTRUCTION


def test_ground_truth_task_for_armoriq():
    """Test that ground truth provides task description for ArmorIQ enforcement."""
    analyzer = PromptAnalyzer()

    analysis = PromptAnalysisResult(
        original_prompt="Search for medical information about diabetes",
        refined_prompt="Search for medical information about diabetes",
        was_refined=False,
        intent=PromptIntent.INSTRUCTION,
        needs_refinement=False,
        latency_ms=12.0,
        analysis_metadata={"mode": "heuristic"}
    )

    ground_truth = analyzer.extract_ground_truth(analysis)

    # Should extract the core task
    assert "Search for medical information" in ground_truth.core_task
    assert ground_truth.domain == "healthcare"
    assert "healthcare" in ground_truth.sensitivity_tags


def test_ground_truth_context_methods():
    """Test GroundTruthContext helper methods."""
    ground_truth = GroundTruthContext(
        original_prompt="What is AI?",
        intent=PromptIntent.QUESTION,
        core_task="is AI?",
        constraints=[],
        entities=["AI"],
        domain="technology",
        sensitivity_tags=[],
        context_requirements=["factual reference material"],
        created_at=1234567890.0,
        confidence=0.8,
    )

    # Test task description
    assert ground_truth.get_task_description() == "is AI?"

    # Test context hints
    hints = ground_truth.get_context_hints()
    assert "factual reference material" in hints

    # Test sensitivity check
    assert not ground_truth.is_sensitive_domain()

    # Test with sensitive domain
    sensitive_gt = ground_truth.model_copy(update={"domain": "healthcare", "sensitivity_tags": ["personal"]})
    assert sensitive_gt.is_sensitive_domain()


def test_prompt_analyzer_extract_core_task():
    """Test the core task extraction logic."""
    analyzer = PromptAnalyzer()

    # Test question
    question_task = analyzer._extract_core_task("What is the capital of France?", PromptIntent.QUESTION)
    assert question_task == "Is the capital of france?"

    # Test instruction
    instruction_task = analyzer._extract_core_task("Find me flights to Paris", PromptIntent.INSTRUCTION)
    assert instruction_task == "Find me flights to paris"

    # Test with action verb
    action_task = analyzer._extract_core_task("Please summarize this article", PromptIntent.INSTRUCTION)
    assert action_task == "Summarize this article"


def test_prompt_analyzer_extract_entities():
    """Test entity extraction from prompts."""
    analyzer = PromptAnalyzer()

    # Test capitalized entities
    entities = analyzer._extract_entities("Find information about Paris and London")
    assert "Paris" in entities
    assert "London" in entities

    # Test numbers
    entities_num = analyzer._extract_entities("Flight 123 departs at 15:30")
    assert "123" in entities_num
    assert "15" in entities_num


def test_prompt_analyzer_infer_domain():
    """Test domain inference from prompt content."""
    analyzer = PromptAnalyzer()

    # Test healthcare domain
    healthcare_domain = analyzer._infer_domain("medical treatment for diabetes", [])
    assert healthcare_domain == "healthcare"

    # Test finance domain
    finance_domain = analyzer._infer_domain("bank account balance", [])
    assert finance_domain == "finance"

    # Test general domain
    general_domain = analyzer._infer_domain("What is the weather?", [])
    assert general_domain == "general"


def test_context_manager_ground_truth_integration():
    """Test full integration of ground truth with ContextManager."""
    mgr = ContextManager()
    analyzer = PromptAnalyzer()

    # Analyze prompt and store ground truth
    analysis = analyzer.analyze("Book a flight to New York")
    ground_truth = analyzer.extract_ground_truth(analysis)
    mgr.store_ground_truth("booking_session", ground_truth)

    # Retrieve task for ArmorIQ
    task = mgr.get_session_task("booking_session")
    assert task is not None
    assert "Book a flight to New York" in task

    # Verify ground truth retrieval
    retrieved_gt = mgr.retrieve_ground_truth("booking_session")
    assert retrieved_gt is not None
    assert retrieved_gt.domain == "travel"
    assert "New York" in retrieved_gt.entities