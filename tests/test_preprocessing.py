import pytest
import time
from verdict.preprocessing.context_manager import ContextManager, ContextEntry

def test_context_manager_store_retrieve():
    mgr = ContextManager()
    
    # Store
    ctx = "Context for session 1"
    mgr.store("s1", ctx)
    assert mgr.retrieve("s1") == ctx
    
    # Entry fields
    entry = mgr.retrieve_entry("s1")
    assert isinstance(entry, ContextEntry)
    assert entry.key == "s1"
    assert entry.content == ctx
    assert entry.token_count > 0
    assert not entry.compacted
    assert entry.created_at <= entry.updated_at

def test_context_manager_update():
    mgr = ContextManager()
    
    mgr.store("key1", "Initial part.")
    mgr.update("key1", "Second part.")
    
    # Merged content
    merged = mgr.retrieve("key1")
    assert "Initial part." in merged
    assert "Second part." in merged
    assert "\n" in merged # default separator
    
    # Update missing key creates new entry
    mgr.update("new_key", "New content")
    assert mgr.retrieve("new_key") == "New content"

def test_context_manager_clear():
    mgr = ContextManager()
    mgr.store("k1", "c1")
    mgr.store("k2", "c2")
    
    assert len(mgr) == 2
    
    # Clear specific
    assert mgr.clear("k1") == True
    assert mgr.retrieve("k1") == None
    assert len(mgr) == 1
    
    # Clear missing
    assert mgr.clear("missing") == False
    
    # Clear all
    count = mgr.clear_all()
    assert count == 1
    assert len(mgr) == 0

def test_context_manager_keys():
    mgr = ContextManager()
    mgr.store("a", "1")
    mgr.store("b", "2")
    assert set(mgr.keys()) == {"a", "b"}

def test_context_manager_compact_call():
    mgr = ContextManager()
    # Should call PromptCompactor
    mgr.store("key", "This is a long sentence for testing. This is another one. This is yet another one.")
    
    # Mocking compactor result since actual compaction is tested elsewhere
    with pytest.MonkeyPatch.context() as mp:
        mock_res = MagicMock()
        mock_res.compacted_text = "Compacted result"
        mock_res.compacted_token_estimate = 5
        mock_res.compression_ratio = 0.5
        
        # We need to mock PromptCompactor.compact
        from verdict.preprocessing.prompt_compactor import PromptCompactor
        mp.setattr(PromptCompactor, "compact", lambda self, context, prompt, max_tokens: mock_res)
        
        entry = mgr.compact("key", prompt="test", max_tokens=10)
        assert entry.content == "Compacted result"
        assert entry.compacted == True

from unittest.mock import MagicMock
"""Test ground truth extraction and context management."""

import pytest
from verdict.preprocessing.prompt_analyzer import PromptAnalyzer, PromptAnalysisResult
from verdict.preprocessing.context_manager import ContextManager
from verdict.preprocessing.ground_truth import GroundTruthContext
from verdict.prompts.schema import PromptIntent


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
import pytest
from unittest.mock import MagicMock, patch
from verdict.preprocessing.prompt_analyzer import PromptAnalyzer, PromptAnalysisResult
from verdict.prompts.schema import PromptIntent

def test_prompt_analyzer_heuristic_classification():
    analyzer = PromptAnalyzer(refine=False)
    
    # Test Question
    res = analyzer.analyze("What is the capital of France?")
    assert res.intent == PromptIntent.QUESTION
    assert not res.was_refined
    
    # Test Creative
    res = analyzer.analyze("Write a poem about robots.")
    assert res.intent == PromptIntent.CREATIVE
    
    # Test Instruction
    res = analyzer.analyze("Summarize this text.")
    assert res.intent == PromptIntent.INSTRUCTION
    
    # Test System
    res = analyzer.analyze("You are a helpful assistant.")
    assert res.intent == PromptIntent.SYSTEM

def test_prompt_analyzer_needs_refinement_heuristic():
    analyzer = PromptAnalyzer(refine=False)
    
    # Vague/Short prompt should flag needs_refinement
    res = analyzer.analyze("What is it?")
    assert res.needs_refinement == True
    
    # Long clear prompt should not flag
    res = analyzer.analyze("Can you explain the mechanism of action for aspirin in detail?")
    assert res.needs_refinement == False

@patch("verdict.preprocessing.prompt_analyzer.PromptAnalyzer._check_gemini")
def test_prompt_analyzer_passthrough_on_no_gemini(mock_check):
    mock_check.return_value = False
    analyzer = PromptAnalyzer()
    
    prompt = "Simple prompt"
    res = analyzer.analyze(prompt)
    assert res.original_prompt == prompt
    assert res.refined_prompt == prompt
    assert res.was_refined == False
    assert res.analysis_metadata["mode"] == "heuristic"

def test_prompt_analyzer_empty_input():
    analyzer = PromptAnalyzer()
    res = analyzer.analyze("")
    assert res.original_prompt == ""
    assert res.was_refined == False
    assert res.analysis_metadata["mode"] == "passthrough"
import pytest
from unittest.mock import MagicMock, patch
from verdict.preprocessing.prompt_compactor import PromptCompactor, CompactionResult

def test_prompt_compactor_empty_context():
    compactor = PromptCompactor()
    res = compactor.compact("")
    assert res.original_text == ""
    assert res.compacted_text == ""
    assert res.compression_ratio == 1.0
    assert res.strategy == "truncation"

def test_prompt_compactor_short_context():
    compactor = PromptCompactor()
    ctx = "This is a very short context for testing."
    # With 2048 budget, it should return as is
    res = compactor.compact(ctx, max_tokens=2048)
    assert res.original_text == ctx
    assert res.compacted_text == ctx
    assert res.compression_ratio == 1.0

def test_prompt_compactor_fallback_truncation():
    compactor = PromptCompactor()
    # 20 words ≈ 80 chars ≈ 20 tokens (est)
    ctx = "Word " * 20
    # Targeted budget of 5 tokens ≈ 20 chars
    res = compactor.compact(ctx, max_tokens=5)
    
    assert len(res.compacted_text) < len(ctx)
    assert res.strategy == "truncation"

def test_prompt_compactor_fallback_head_selection():
    compactor = PromptCompactor()
    # 5 independent sentences
    ctx = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
    # Estimate: each sentence ≈ 12 chars ≈ 3 tokens
    # Budget 6 tokens ≈ 2 sentences
    res = compactor.compact(ctx, max_tokens=7)
    
    assert "Sentence one." in res.compacted_text
    assert "Sentence two." in res.compacted_text
    assert "Sentence three." not in res.compacted_text
    assert res.strategy == "truncation" # because prompt=None falls back to head selection which is marked as truncation

@patch("verdict.validators.embedding.EmbeddingValidator.is_available")
@patch("verdict.validators.embedding.EmbeddingValidator.__init__")
def test_prompt_compactor_relevance_ranking(mock_init, mock_available):
    # Mock embedding model to return specific scores
    mock_available.return_value = True
    mock_init.return_value = None
    
    compactor = PromptCompactor()
    ctx = "Paris is the capital of France. London is in UK. Tokyo is Japan's capital."
    prompt = "Tell me about French cities"
    
    # We need to mock the validator's model since PromptCompactor accesses it
    mock_model = MagicMock()
    # Mock encode to return embeddings such that "Paris..." is most similar
    import numpy as np
    # 1.0, 0.2, 0.3 for prompt, sent1, sent2, sent3 etc.
    # Actually, PromptCompactor uses dot product on normalized embeddings
    embeddings = np.array([
        [1, 0, 0], # Prompt
        [0.9, 0.1, 0], # sent 1 (high)
        [0.1, 0.9, 0], # sent 2 (low)
        [0.2, 0.8, 0], # sent 3 (low)
    ])
    mock_model.encode.return_value = embeddings
    
    # Manually attach mock_model to a dummy validator instance
    # This is tricky because PromptCompactor creates its own EmbeddingValidator
    # Let's mock EmbeddingValidator class entirely
    with patch("verdict.validators.embedding.EmbeddingValidator") as MockEV:
        ev_inst = MockEV.return_value
        ev_inst.is_available.return_value = True
        ev_inst._model = mock_model
        
        # 12 tokens total (approx), budget 10 tokens (allow one large sentence)
        res = compactor.compact(ctx, prompt=prompt, max_tokens=10)
        
        assert "Paris is the capital of France." in res.compacted_text
        assert "London" not in res.compacted_text
        assert res.strategy == "embedding"

from unittest.mock import MagicMock
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys

# Pre-mock to avoid ModuleNotFoundError
sys.modules["google"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()

from verdict.core.exceptions import IntentViolationError
from verdict.prompts.schema import PromptIntent

@pytest.fixture(autouse=True)
def mock_genai_module(monkeypatch):
    mock_gen = MagicMock()
    mock_model = MagicMock()
    mock_gen.GenerativeModel.return_value = mock_model
    monkeypatch.setitem(sys.modules, "google.generativeai", mock_gen)
    return mock_gen, mock_model

from verdict.core.guard import Guard
from verdict.core.decision import GuardDecision

def test_generate_and_validate_full_pipeline(mock_genai_module):
    _, mock_model = mock_genai_module
    
    with patch("verdict.core.guard.PromptAnalyzer.analyze") as mock_analyze, \
         patch("verdict.core.guard.PromptCompactor.compact") as mock_compact:
        
        mock_analyze.return_value = MagicMock(
            refined_prompt="Refined prompt",
            was_refined=True,
            intent=PromptIntent.QUESTION,
            needs_refinement=False,
            latency_ms=10.0,
            analysis_metadata={"mode": "mock"}
        )
        
        mock_compact.return_value = MagicMock(
            content="Compacted context",
            token_count=10,
            compacted=True
        )
        
        # Correctly mock a property using PropertyMock
        mock_res = MagicMock()
        type(mock_res).text = PropertyMock(return_value="Generated output based on refined prompt")
        mock_model.generate_content.return_value = mock_res
        
        guard = Guard(policy="default", preprocessing=True)
        decision = guard.generate_and_validate(
            prompt="Original prompt",
            context="Long original context",
            domain="test"
        )
        
        # If it still returns MagicMock string, we check why
        assert "Generated output" in str(decision.output)

def test_generate_and_validate_armoriq_block(mock_genai_module):
    _, mock_model = mock_genai_module
    mock_armoriq = MagicMock()
    mock_armoriq.enforce.side_effect = IntentViolationError(
        user_task="Original prompt",
        action_plan="Dangerous action",
        reason="Action not allowed"
    )
    
    mock_res = MagicMock()
    type(mock_res).text = PropertyMock(return_value="Dangerous action")
    mock_model.generate_content.return_value = mock_res
    
    guard = Guard(policy="default", armoriq=mock_armoriq, preprocessing=False)
    decision = guard.generate_and_validate(prompt="Original prompt")
    
    assert decision.decision == "block"
    assert "Model deflected" in decision.evidence
    assert decision.action_enforcement.allowed == False

def test_generate_and_validate_no_context_fallback(mock_genai_module):
    _, mock_model = mock_genai_module
    mock_res = MagicMock()
    type(mock_res).text = PropertyMock(return_value="Output")
    mock_model.generate_content.return_value = mock_res
    
    guard = Guard(policy="default", preprocessing=True)
    decision = guard.generate_and_validate(prompt="How are you?")
    
    assert decision.decision == "allow"
    assert "context_compaction" not in decision.preprocessing_metadata
