"""Tests for ArmorIQ intent enforcement adapter."""

import pytest
from hallucination_guard.integrations.armoriq import ArmorIQAdapter
from hallucination_guard.core.exceptions import IntentViolationError


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

    def test_exception_is_hallucination_guard_error(self):
        """Test that IntentViolationError is a HallucinationGuardError."""
        from hallucination_guard.core.exceptions import HallucinationGuardError
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
