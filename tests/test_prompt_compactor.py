import pytest
from unittest.mock import MagicMock, patch
from hallucination_guard.preprocessing.prompt_compactor import PromptCompactor, CompactionResult

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

@patch("hallucination_guard.validators.embedding.EmbeddingValidator.is_available")
@patch("hallucination_guard.validators.embedding.EmbeddingValidator.__init__")
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
    with patch("hallucination_guard.validators.embedding.EmbeddingValidator") as MockEV:
        ev_inst = MockEV.return_value
        ev_inst.is_available.return_value = True
        ev_inst._model = mock_model
        
        # 12 tokens total (approx), budget 10 tokens (allow one large sentence)
        res = compactor.compact(ctx, prompt=prompt, max_tokens=10)
        
        assert "Paris is the capital of France." in res.compacted_text
        assert "London" not in res.compacted_text
        assert res.strategy == "embedding"

from unittest.mock import MagicMock
