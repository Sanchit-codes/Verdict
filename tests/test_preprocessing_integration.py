import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys

# Pre-mock to avoid ModuleNotFoundError
sys.modules["google"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()

from hallucination_guard.core.exceptions import IntentViolationError
from hallucination_guard.prompts.schema import PromptIntent

@pytest.fixture(autouse=True)
def mock_genai_module(monkeypatch):
    mock_gen = MagicMock()
    mock_model = MagicMock()
    mock_gen.GenerativeModel.return_value = mock_model
    monkeypatch.setitem(sys.modules, "google.generativeai", mock_gen)
    return mock_gen, mock_model

from hallucination_guard.core.guard import Guard
from hallucination_guard.core.decision import GuardDecision

def test_generate_and_validate_full_pipeline(mock_genai_module):
    _, mock_model = mock_genai_module
    
    with patch("hallucination_guard.core.guard.PromptAnalyzer.analyze") as mock_analyze, \
         patch("hallucination_guard.core.guard.PromptCompactor.compact") as mock_compact:
        
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
