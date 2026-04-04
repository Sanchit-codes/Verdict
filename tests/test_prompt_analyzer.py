import pytest
from unittest.mock import MagicMock, patch
from hallucination_guard.preprocessing.prompt_analyzer import PromptAnalyzer, PromptAnalysisResult
from hallucination_guard.prompts.schema import PromptIntent

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

@patch("hallucination_guard.preprocessing.prompt_analyzer.PromptAnalyzer._check_gemini")
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
