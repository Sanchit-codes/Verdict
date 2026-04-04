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

from hallucination_guard.integrations.armoriq import (
    ArmorIQAdapter,
    RuleBasedArmorIQClient,
)
from hallucination_guard.core.decision import ActionEnforcementResult, GuardDecision
from hallucination_guard.core.exceptions import IntentViolationError


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
        from hallucination_guard.core.guard import Guard
        adapter = make_adapter(enforcement)
        return Guard(policy="default", armoriq=adapter)

    def test_guard_init_without_armoriq(self):
        from hallucination_guard.core.guard import Guard
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
        from hallucination_guard.core.guard import Guard
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
            from hallucination_guard.integrations.langchain import HallucinationGuardCallback
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
            from hallucination_guard.integrations.langchain import HallucinationGuardCallback
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
            from hallucination_guard.integrations.langchain import HallucinationGuardCallback
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
            from hallucination_guard.integrations.langchain import HallucinationGuardCallback
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
