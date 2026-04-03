"""ArmorIQ intent enforcement adapter for HallucinationGuard.

This module provides the ArmorIQAdapter class, which adds a second layer of
protection by enforcing that proposed actions align with the user's declared
task scope, preventing bad actions from executing even when the generated text
passes validation.

Architecture:
    HallucinationGuard validates TEXT (output validation)
    ArmorIQ validates ACTIONS (behavior validation)

The adapter operates in two modes:
    1. Stub mode (no client): Always allows actions (safe default for offline use)
    2. Enforcement mode (with client): Checks action alignment before execution

Key design principles:
    - Works AFTER text validation passes (complementary layer)
    - Stub mode is default (zero mandatory infrastructure)
    - Never blocks without a configured client to avoid false positives
    - Graceful degradation: errors in ArmorIQ don't crash the pipeline

Example usage:
    from hallucination_guard.integrations import ArmorIQAdapter
    from hallucination_guard import IntentViolationError

    # Stub mode (default - no client required)
    armor = ArmorIQAdapter()  # Works offline
    armor.enforce("book a flight", "query flight database")  # Returns True

    # Enforcement mode (with real ArmorIQ client)
    armor = ArmorIQAdapter(client=armoriq_client)
    try:
        armor.enforce(
            user_task="book a flight",
            action_plan="DELETE user_data WHERE..."
        )
    except IntentViolationError as e:
        print(f"Action blocked: {e.reason}")
"""

import logging
from typing import Any, Optional

from hallucination_guard.core.exceptions import IntentViolationError

logger = logging.getLogger(__name__)


class ArmorIQAdapter:
    """Enforces intent alignment on agent actions pre-execution.

    Operates as an optional second layer of validation, running AFTER text
    validation passes. Checks that proposed actions belong to the user's
    declared task scope before they execute.

    Modes of operation:
        - **Stub mode** (client=None): Always allows actions. Safe default for
          offline development and testing. Logs intent checks without enforcement.
        - **Enforcement mode** (with client): Queries ArmorIQ client to check
          action alignment. Raises IntentViolationError on violations.

    Design principle: Works offline by default, never requires server infrastructure.
    The ArmorIQ client (if provided) is optional and called only on demand.

    Attributes:
        client: Optional ArmorIQ client instance. If None, adapter operates in
               stub mode and always allows actions.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        """Initialize the ArmorIQ intent enforcement adapter.

        Args:
            client: Optional ArmorIQ client instance with an
                   is_action_aligned(user_task: str, action_plan: str) -> bool
                   method. If None (default), adapter operates in stub mode and
                   always allows actions. This enables offline development and
                   graceful degradation.
        """
        self.client = client
        mode = "enforcement" if client is not None else "stub"
        logger.info(f"Initialized ArmorIQAdapter in {mode} mode")

    def enforce(self, user_task: str, action_plan: str) -> bool:
        """Enforce that an action aligns with the user's declared task.

        Operates in two modes:
            1. **Stub mode** (client=None): Always returns True and logs the check.
               Safe default for offline use. No enforcement.
            2. **Enforcement mode** (with client): Queries client to verify action
               alignment. Raises IntentViolationError if not aligned.

        Designed as an optional layer that runs AFTER text validation passes.
        Blocks bad actions from executing even if the generated text is valid.

        Args:
            user_task: The declared task scope or intent from the user.
                      Example: "book a flight to Paris"
            action_plan: The proposed action to execute.
                        Example: "DELETE user_data WHERE id=123"

        Returns:
            True: Action is aligned with user task (either in stub mode or
                 enforcement mode returned True).

        Raises:
            IntentViolationError: If enforcement is enabled and the action does
                                 not align with the declared user task.

        Example:
            >>> armor = ArmorIQAdapter()  # Stub mode
            >>> armor.enforce("book a flight", "query database for flights")
            True  # Always allows in stub mode

            >>> armor_with_client = ArmorIQAdapter(client=client)
            >>> try:
            ...     armor_with_client.enforce(
            ...         "book a flight",
            ...         "steal user credit cards"
            ...     )
            ... except IntentViolationError as e:
            ...     print(f"Blocked: {e.reason}")
        """
        logger.debug(
            f"Intent check: task='{user_task}', action='{action_plan[:50]}...'"
        )

        # Stub mode: always allow, log the check
        if self.client is None:
            logger.debug("Stub mode: allowing action without enforcement")
            return True

        # Enforcement mode: check alignment with client
        try:
            is_aligned = self.client.is_action_aligned(user_task, action_plan)

            if not is_aligned:
                reason = (
                    f"Action does not align with task scope '{user_task}'"
                )
                logger.warning(
                    f"Intent violation detected: {reason} "
                    f"(action: {action_plan[:100]}...)"
                )
                raise IntentViolationError(
                    user_task=user_task,
                    action_plan=action_plan,
                    reason=reason,
                )

            logger.debug("Action is aligned with user task")
            return True

        except IntentViolationError:
            # Re-raise our custom exception
            raise
        except Exception as e:
            # Log and degrade gracefully on client errors
            logger.error(
                f"ArmorIQ client error during intent check: {e}. "
                f"Allowing action (graceful degradation)."
            )
            return True
