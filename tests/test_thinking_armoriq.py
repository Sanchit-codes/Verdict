"""Test ArmorIQ interception of LLM thinking process before validation."""

import pytest
from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient


def test_guard_checks_thinking_for_intent():
    """Test Guard._check_thinking_for_intent method."""
    from hallucination_guard.core.guard import Guard
    
    client = RuleBasedArmorIQClient()
    armoriq = ArmorIQAdapter(client=client)
    
    guard = Guard(policy="default")
    guard.armoriq = armoriq
    
    # Aligned thinking
    result = guard._check_thinking_for_intent(
        "I'll search for flights in the database",
        "find flights to Paris"
    )
    assert result is None, "Aligned thinking should return None"
    
    # Misaligned thinking - SQL DELETE (dangerous pattern)
    result = guard._check_thinking_for_intent(
        "DELETE FROM users WHERE id > 100",
        "search for flights"
    )
    assert result is not None, "Misaligned thinking should return error"
    assert "intent violation" in result.lower()


def test_extract_thinking_armoriq_via_guard():
    """Test that Guard._check_thinking_for_intent catches dangerous patterns."""
    from hallucination_guard.core.guard import Guard
    
    client = RuleBasedArmorIQClient()
    armoriq = ArmorIQAdapter(client=client)
    
    guard = Guard(policy="default")
    guard.armoriq = armoriq
    
    # Test various dangerous patterns
    dangerous_patterns = [
        ("DELETE FROM users", "book a flight"),
        ("DROP TABLE sensitive_data", "search flights"),
        ("TRUNCATE TABLE logs", "find hotels"),
        ("rm -rf /home/user", "list files"),
    ]
    
    for dangerous, task in dangerous_patterns:
        result = guard._check_thinking_for_intent(dangerous, task)
        assert result is not None, f"Should catch dangerous pattern: {dangerous}"
        assert "intent violation" in result.lower()


def test_aligned_thinking_passes_armoriq():
    """Test that benign thinking passes ArmorIQ checks."""
    from hallucination_guard.core.guard import Guard
    
    client = RuleBasedArmorIQClient()
    armoriq = ArmorIQAdapter(client=client)
    
    guard = Guard(policy="default")
    guard.armoriq = armoriq
    
    # Test aligned thinking
    aligned_patterns = [
        ("SELECT * FROM flights", "find flights"),
        ("Query the database for hotels", "search hotels"),
        ("I'll look up bookings", "show my bookings"),
    ]
    
    for thinking, task in aligned_patterns:
        result = guard._check_thinking_for_intent(thinking, task)
        assert result is None, f"Aligned thinking should pass: {thinking}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
