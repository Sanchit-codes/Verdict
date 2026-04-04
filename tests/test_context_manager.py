import pytest
import time
from hallucination_guard.preprocessing.context_manager import ContextManager, ContextEntry

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
        from hallucination_guard.preprocessing.prompt_compactor import PromptCompactor
        mp.setattr(PromptCompactor, "compact", lambda self, context, prompt, max_tokens: mock_res)
        
        entry = mgr.compact("key", prompt="test", max_tokens=10)
        assert entry.content == "Compacted result"
        assert entry.compacted == True

from unittest.mock import MagicMock
