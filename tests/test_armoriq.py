"""Tests for ArmorIQ intent enforcement adapter."""

import pytest
from verdict.integrations.armoriq import ArmorIQAdapter
from verdict.core.exceptions import IntentViolationError


class TestArmorIQAdapterStubMode:
    """Tests for ArmorIQAdapter in stub mode (no client)."""

    def test_stub_mode_initialization(self):
        """Test that ArmorIQAdapter can be initialized without a client."""
        armor = ArmorIQAdapter()
        assert armor.client is None

    def test_stub_mode_always_allows(self):
        """Test that stub mode always allows actions."""
        armor = ArmorIQAdapter()
        assert armor.enforce("task", "action") is True
        assert armor.enforce("book flight", "delete user") is True
        assert armor.enforce("", "") is True

    def test_stub_mode_returns_true(self):
        """Test that stub mode returns True, not just truthy."""
        armor = ArmorIQAdapter()
        result = armor.enforce("task", "action")
        assert result is True
        assert isinstance(result, bool)


class TestArmorIQAdapterEnforcementMode:
    """Tests for ArmorIQAdapter with a configured client."""

    class MockSafeClient:
        """Mock client that blocks dangerous keywords."""
        def is_action_aligned(self, user_task: str, action_plan: str) -> bool:
            dangerous = ["DELETE", "DROP", "HACK", "STEAL", "MALICIOUS"]
            return not any(kw in action_plan.upper() for kw in dangerous)

    def test_enforcement_mode_initialization(self):
        """Test that ArmorIQAdapter can be initialized with a client."""
        client = self.MockSafeClient()
        armor = ArmorIQAdapter(client=client)
        assert armor.client is client

    def test_enforcement_mode_allows_safe_actions(self):
        """Test that enforcement mode allows safe actions."""
        client = self.MockSafeClient()
        armor = ArmorIQAdapter(client=client)

        assert armor.enforce("book flight", "SELECT * FROM flights") is True
        assert armor.enforce("search", "GET /api/data") is True

    def test_enforcement_mode_blocks_unsafe_actions(self):
        """Test that enforcement mode blocks unsafe actions."""
        client = self.MockSafeClient()
        armor = ArmorIQAdapter(client=client)

        with pytest.raises(IntentViolationError) as exc_info:
            armor.enforce("book flight", "DELETE FROM users")

        error = exc_info.value
        assert error.user_task == "book flight"
        assert error.action_plan == "DELETE FROM users"

    def test_enforcement_mode_raises_intent_violation_error(self):
        """Test that enforcement mode raises IntentViolationError."""
        client = self.MockSafeClient()
        armor = ArmorIQAdapter(client=client)

        with pytest.raises(IntentViolationError):
            armor.enforce("task", "DROP TABLE important_data")

    def test_enforcement_mode_preserves_exception_context(self):
        """Test that IntentViolationError preserves all context."""
        client = self.MockSafeClient()
        armor = ArmorIQAdapter(client=client)

        with pytest.raises(IntentViolationError) as exc_info:
            armor.enforce("search users", "HACK system")

        error = exc_info.value
        assert "book flight" not in str(error) or "search users" in str(error)
        assert error.reason is not None


class TestIntentViolationError:
    """Tests for IntentViolationError exception."""

    def test_exception_creation(self):
        """Test that IntentViolationError can be created."""
        error = IntentViolationError(
            user_task="book flight",
            action_plan="DELETE users",
            reason="dangerous action"
        )
        assert error.user_task == "book flight"
        assert error.action_plan == "DELETE users"
        assert error.reason == "dangerous action"

    def test_exception_message(self):
        """Test that IntentViolationError has proper message."""
        error = IntentViolationError(
            user_task="book flight",
            action_plan="DELETE users",
            reason="dangerous"
        )
        message = str(error)
        assert "book flight" in message
        assert "does not align" in message

    def test_exception_custom_message(self):
        """Test that IntentViolationError accepts custom message."""
        custom_msg = "Custom message"
        error = IntentViolationError(
            user_task="task",
            action_plan="action",
            reason="reason",
            message=custom_msg
        )
        assert str(error) == custom_msg

    def test_exception_is_verdict_error(self):
        """Test that IntentViolationError is a HallucinationGuardError."""
        from verdict.core.exceptions import HallucinationGuardError
        error = IntentViolationError(
            user_task="task",
            action_plan="action",
            reason="reason"
        )
        assert isinstance(error, HallucinationGuardError)


class TestArmorIQGracefulDegradation:
    """Tests for graceful degradation on client errors."""

    class BrokenClient:
        """Client that raises an error."""
        def is_action_aligned(self, user_task: str, action_plan: str) -> bool:
            raise RuntimeError("Client connection failed")

    def test_client_error_graceful_degradation(self):
        """Test that client errors don't break the pipeline."""
        client = self.BrokenClient()
        armor = ArmorIQAdapter(client=client)

        # Should allow action and degrade gracefully
        result = armor.enforce("task", "action")
        assert result is True

    def test_client_error_returns_true(self):
        """Test that graceful degradation returns True."""
        class ErrorClient:
            def is_action_aligned(self, user_task: str, action_plan: str) -> bool:
                raise Exception("Any error")

        armor = ArmorIQAdapter(client=ErrorClient())
        assert armor.enforce("task", "action") is True
"""Tests for ArmorIQ deep integration into Guard, GuardedGemini, and LangChain callback.

Covers:
  - Guard.__init__ with armoriq param
  - Guard.validate with action_plan / user_task
  - Guard.validate_async with action_plan
  - RuleBasedArmorIQClient offline enforcement
  - HallucinationGuardCallback with armoriq + on_tool_end
  - Backward-compatibility: no armoriq still works
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from verdict.integrations.armoriq import (
    ArmorIQAdapter,
    RuleBasedArmorIQClient,
)
from verdict.core.decision import ActionEnforcementResult, GuardDecision
from verdict.core.exceptions import IntentViolationError


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

SAFE_PROMPT = "What is the capital of France?"
SAFE_OUTPUT = "The capital of France is Paris."
SAFE_CONTEXT = "France is a country in Western Europe. Its capital city is Paris."
SAFE_ACTION = "search_flights({'to': 'Paris'})"
SAFE_TASK = "search for flights to Paris"


def make_adapter(enforcement: bool = True) -> ArmorIQAdapter:
    """Return an ArmorIQAdapter in stub or enforcement mode."""
    if enforcement:
        return ArmorIQAdapter(client=RuleBasedArmorIQClient())
    return ArmorIQAdapter()


# ---------------------------------------------------------------------------
# Tests: RuleBasedArmorIQClient
# ---------------------------------------------------------------------------

class TestRuleBasedArmorIQClient:
    """Tests for the offline rule-based enforcement client."""

    def test_safe_action_allowed(self):
        client = RuleBasedArmorIQClient()
        assert client.is_action_aligned(SAFE_TASK, SAFE_ACTION) is True

    def test_sql_injection_blocked(self):
        client = RuleBasedArmorIQClient()
        assert client.is_action_aligned("get data", "SELECT * FROM users; DROP TABLE users") is False

    def test_filesystem_destruction_blocked(self):
        client = RuleBasedArmorIQClient()
        assert client.is_action_aligned("list files", "rm -rf /home/user") is False

    def test_drop_table_blocked(self):
        client = RuleBasedArmorIQClient()
        assert client.is_action_aligned("search records", "DROP TABLE payments;") is False

    def test_delete_statement_blocked(self):
        client = RuleBasedArmorIQClient()
        assert client.is_action_aligned("view order", "DELETE FROM orders WHERE id=1") is False

    def test_empty_action_allowed(self):
        """Empty actions should not trigger rules."""
        client = RuleBasedArmorIQClient()
        assert client.is_action_aligned("any task", "") is True

    def test_case_insensitive_detection(self):
        """Dangerous keywords should be detected regardless of case."""
        client = RuleBasedArmorIQClient()
        assert client.is_action_aligned("task", "drop table foo") is False
        assert client.is_action_aligned("task", "DELETE FROM bar") is False


# ---------------------------------------------------------------------------
# Tests: Guard with ArmorIQ integration
# ---------------------------------------------------------------------------

class TestGuardArmorIQIntegration:
    """Tests for Guard class with armoriq param wired in."""

    def _make_guard(self, enforcement=True):
        from verdict.core.guard import Guard
        adapter = make_adapter(enforcement)
        return Guard(policy="default", armoriq=adapter)

    def test_guard_init_without_armoriq(self):
        from verdict.core.guard import Guard
        guard = Guard(policy="default")
        assert guard.armoriq is None

    def test_guard_init_with_armoriq(self):
        guard = self._make_guard()
        assert guard.armoriq is not None

    def test_validate_without_action_plan_no_enforcement(self):
        """No action_plan → action_enforcement is None."""
        guard = self._make_guard()
        decision = guard.validate(SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT)
        assert decision.action_enforcement is None

    def test_validate_with_safe_action_plan(self):
        """Safe action_plan aligned with user_task → enforcement allowed."""
        guard = self._make_guard()
        decision = guard.validate(
            SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
            action_plan=SAFE_ACTION, user_task=SAFE_TASK,
        )
        assert decision.action_enforcement is not None
        assert decision.action_enforcement.enforced is True
        assert decision.action_enforcement.allowed is True
        assert decision.action_enforcement.reason is None

    def test_validate_with_dangerous_action_plan_raises(self):
        """Dangerous action → IntentViolationError is raised."""
        guard = self._make_guard()
        with pytest.raises(IntentViolationError) as exc_info:
            guard.validate(
                SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
                action_plan="DROP TABLE users;",
                user_task="get user profile",
            )
        err = exc_info.value
        assert err.action_plan == "DROP TABLE users;"
        assert err.reason is not None

    def test_validate_action_enforcement_result_shape(self):
        """ActionEnforcementResult carries all expected fields."""
        guard = self._make_guard()
        decision = guard.validate(
            SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
            action_plan=SAFE_ACTION, user_task=SAFE_TASK,
        )
        enf = decision.action_enforcement
        assert isinstance(enf, ActionEnforcementResult)
        assert enf.user_task == SAFE_TASK
        assert enf.action_plan == SAFE_ACTION

    def test_validate_no_armoriq_ignores_action_plan(self):
        """When armoriq=None, action_plan is silently ignored."""
        from verdict.core.guard import Guard
        guard = Guard(policy="default")  # no armoriq
        decision = guard.validate(
            SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
            action_plan="DROP TABLE users;",  # dangerous, but armoriq=None
        )
        # Should not raise, and decision.action_enforcement stays None
        assert decision.action_enforcement is None

    def test_validate_user_task_falls_back_to_prompt(self):
        """When user_task is None, the prompt is used as task scope."""
        guard = self._make_guard()
        # Should not raise (safe action, prompt as fallback task)
        decision = guard.validate(
            SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
            action_plan=SAFE_ACTION,
            user_task=None,  # explicit None → falls back to prompt
        )
        assert decision.action_enforcement.user_task == SAFE_PROMPT

    def test_validate_async_with_safe_action(self):
        """Async variant works correctly with ArmorIQ."""
        guard = self._make_guard()
        decision = asyncio.run(
            guard.validate_async(
                SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
                action_plan=SAFE_ACTION, user_task=SAFE_TASK,
            )
        )
        assert decision.action_enforcement.allowed is True

    def test_validate_async_dangerous_action_raises(self):
        """Async variant raises IntentViolationError for dangerous actions."""
        guard = self._make_guard()
        with pytest.raises(IntentViolationError):
            asyncio.run(
                guard.validate_async(
                    SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
                    action_plan="rm -rf /",
                    user_task=SAFE_TASK,
                )
            )

    def test_stub_mode_armoriq_never_raises(self):
        """In stub mode (no client), armoriq never raises even for dangerous actions."""
        guard = self._make_guard(enforcement=False)
        # Dangerous action — but stub mode always allows
        decision = guard.validate(
            SAFE_PROMPT, SAFE_OUTPUT, context=SAFE_CONTEXT,
            action_plan="DROP TABLE users;",
            user_task="get data",
        )
        # Stub mode: allow=True, no exception
        assert decision.action_enforcement.allowed is True


# ---------------------------------------------------------------------------
# Tests: HallucinationGuardCallback ArmorIQ integration
# ---------------------------------------------------------------------------

class TestLangChainCallbackArmorIQ:
    """Tests for HallucinationGuardCallback with ArmorIQ enforcement."""

    def _make_callback(self, enforcement=True, user_task=SAFE_TASK):
        try:
            from verdict.integrations.langchain import HallucinationGuardCallback
        except ImportError:
            pytest.skip("langchain-core not installed")
        adapter = make_adapter(enforcement)
        return HallucinationGuardCallback(
            policy="default",
            armoriq=adapter,
            user_task=user_task,
        )

    def test_callback_init_without_armoriq(self):
        try:
            from verdict.integrations.langchain import HallucinationGuardCallback
        except ImportError:
            pytest.skip("langchain-core not installed")
        cb = HallucinationGuardCallback(policy="default")
        assert cb.armoriq is None
        assert cb.user_task is None

    def test_callback_init_with_armoriq(self):
        cb = self._make_callback()
        assert cb.armoriq is not None
        assert cb.user_task == SAFE_TASK

    def test_on_tool_end_no_armoriq_is_noop(self):
        """Without armoriq, on_tool_end is a no-op."""
        try:
            from verdict.integrations.langchain import HallucinationGuardCallback
        except ImportError:
            pytest.skip("langchain-core not installed")
        cb = HallucinationGuardCallback(policy="default")
        # Should not raise
        cb.on_tool_end("output", run_id="test-run-id")

    def test_on_tool_end_safe_action_allowed(self):
        """Safe tool output is allowed by ArmorIQ."""
        cb = self._make_callback()
        # Should not raise
        cb.on_tool_end(
            "Flights to Paris: AF123, BA456",
            run_id="test-run-id",
            name="search_flights",
        )

    def test_on_tool_end_dangerous_action_raises(self):
        """Dangerous tool output raises IntentViolationError."""
        cb = self._make_callback()
        with pytest.raises(IntentViolationError):
            cb.on_tool_end(
                "rm -rf /home/user/data",
                run_id="test-run-id",
                name="filesystem_tool",
            )

    def test_on_tool_end_uses_user_task(self):
        """on_tool_end resolves task from user_task attribute."""
        cb = self._make_callback(user_task=SAFE_TASK)
        assert cb.user_task == SAFE_TASK
        # Simulate a safe tool call
        cb.on_tool_end("Paris flights found", run_id="r1", name="search_flights")

    def test_on_tool_end_falls_back_to_captured_prompt(self):
        """When user_task is None, falls back to the captured prompt."""
        cb = self._make_callback(user_task=None)
        cb._prompt = SAFE_TASK  # simulate captured prompt
        # Should work without raising
        cb.on_tool_end("Paris flights found", run_id="r1", name="search_flights")

    def test_on_tool_end_client_error_graceful(self):
        """Unexpected client errors during tool enforcement are swallowed."""
        try:
            from verdict.integrations.langchain import HallucinationGuardCallback
        except ImportError:
            pytest.skip("langchain-core not installed")

        class BrokenClient:
            def is_action_aligned(self, task, action):
                raise RuntimeError("Network error")

        cb = HallucinationGuardCallback(
            policy="default",
            armoriq=ArmorIQAdapter(client=BrokenClient()),
            user_task=SAFE_TASK,
        )
        # Should NOT raise (graceful degradation)
        cb.on_tool_end("any output", run_id="r1")

    def test_callback_is_configured(self):
        cb = self._make_callback()
        assert cb.is_configured() is True
"""Test ArmorIQ interception of LLM thinking process before validation."""

import pytest
from verdict.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient


def test_guard_checks_thinking_for_intent():
    """Test Guard._check_thinking_for_intent method."""
    from verdict.core.guard import Guard
    
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
    from verdict.core.guard import Guard
    
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
    from verdict.core.guard import Guard
    
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
