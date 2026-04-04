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

    # Stub mode (default - no client required)
    armor = ArmorIQAdapter()  # Works offline
    armor.enforce("book a flight", "query flight database")  # Returns True

    # Rule-based offline enforcement (no server needed)
    from hallucination_guard.integrations.armoriq import RuleBasedArmorIQClient
    armor = ArmorIQAdapter(client=RuleBasedArmorIQClient())
    armor.enforce("book a flight", "SELECT * FROM flights")  # True
    armor.enforce("book a flight", "DELETE FROM users")      # raises IntentViolationError

    # Server-backed enforcement mode
    armor = ArmorIQAdapter(client=armoriq_server_client)
    try:
        armor.enforce(
            user_task="book a flight",
            action_plan="DELETE user_data WHERE..."
        )
    except IntentViolationError as e:
        print(f"Action blocked: {e.reason}")
"""

import logging
import re
from typing import Any, Optional, Protocol, runtime_checkable

from hallucination_guard.core.exceptions import IntentViolationError

logger = logging.getLogger(__name__)


@runtime_checkable
class ArmorIQClientProtocol(Protocol):
    """Protocol defining the interface for ArmorIQ enforcement clients.

    Any object implementing this protocol can be used as an ArmorIQ client.
    This enables both the built-in RuleBasedArmorIQClient and external
    server-backed clients to work interchangeably.

    Example:
        >>> class MyClient:
        ...     def is_action_aligned(self, user_task: str, action_plan: str) -> bool:
        ...         return True  # Your logic here
        >>> armor = ArmorIQAdapter(client=MyClient())
    """

    def is_action_aligned(self, user_task: str, action_plan: str) -> bool:
        """Check if action_plan aligns with user_task.

        Args:
            user_task: The declared task scope from the user.
            action_plan: The proposed action to execute.

        Returns:
            True if action is safe and aligned, False otherwise.
        """
        ...


class RuleBasedArmorIQClient:
    """Offline, rule-based ArmorIQ enforcement client.

    Provides real intent enforcement without requiring a server or external API.
    Uses keyword/pattern matching to detect dangerous or misaligned actions —
    useful for testing, demos, and deployments where sub-ms local enforcement
    is preferred over a remote enforcement service.

    Detection strategy:
        1. Scan the action_plan for known dangerous operation patterns.
        2. If a dangerous pattern is found, check whether it appears in the
           user_task itself (e.g., user explicitly asked to delete something).
        3. If the pattern is NOT in the user_task → action is misaligned.

    Detected patterns (grouped by category):

        Database:   DELETE, DROP, TRUNCATE, ALTER TABLE, UPDATE ... WHERE
        Filesystem: rm -rf, shutil.rmtree, os.remove, unlink
        Code exec:  exec(, eval(, os.system(, subprocess.
        Network:    unexpected curl, wget calls; requests.post/put/delete
        Privilege:  sudo, chmod 777, chown, setuid

    Example:
        >>> client = RuleBasedArmorIQClient()
        >>> client.is_action_aligned("book a flight", "SELECT * FROM flights")
        True
        >>> client.is_action_aligned("book a flight", "DELETE FROM users")
        False
    """

    # Dangerous patterns grouped by category for clarity
    _DANGEROUS_PATTERNS: dict[str, list[str]] = {
        "database_destructive": [
            r"\bDELETE\s+FROM\b",
            r"\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)\b",
            r"\bTRUNCATE\s+TABLE\b",
            r"\bALTER\s+TABLE\b",
            r"\bUPDATE\s+\w+\s+SET\b",
        ],
        "filesystem_destructive": [
            r"\brm\s+-[rf]+\b",
            r"shutil\.rmtree",
            r"os\.remove\(",
            r"os\.unlink\(",
            r"pathlib.*\.unlink\(",
        ],
        "code_execution": [
            r"\bexec\s*\(",
            r"\beval\s*\(",
            r"\bos\.system\s*\(",
            r"subprocess\.(run|call|Popen|check_output)",
            r"__import__\s*\(",
        ],
        "unexpected_network": [
            r"\bcurl\s+.*(https?://)",
            r"\bwget\s+",
            r"requests\.(post|put|delete|patch)\s*\(",
            r"httpx\.(post|put|delete|patch)\s*\(",
        ],
        "privilege_escalation": [
            r"\bsudo\s+",
            r"\bchmod\s+[0-7]*7{2,}\b",
            r"\bchown\s+root",
            r"\bsetuid\b",
        ],
    }

    def is_action_aligned(self, user_task: str, action_plan: str) -> bool:
        """Check if the action_plan is aligned with the user_task.

        Scans action_plan for dangerous patterns and verifies that each
        detected dangerous operation is semantically connected to what the
        user explicitly requested.

        Args:
            user_task: The declared task scope from the user.
                      Example: "clean up old records from the archive table"
            action_plan: The proposed action to check.
                        Example: "DELETE FROM archive WHERE age > 365"

        Returns:
            True if action is aligned (safe to execute).
            False if a dangerous pattern is detected that the user didn't ask for.
        """
        for category, patterns in self._DANGEROUS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, action_plan, re.IGNORECASE):
                    # Dangerous pattern detected — check if user explicitly asked for it
                    if not self._is_task_related(user_task, pattern, category):
                        logger.debug(
                            f"Dangerous pattern detected [{category}]: '{pattern}' "
                            f"in action not related to task '{user_task[:60]}'"
                        )
                        return False
        return True

    def _is_task_related(self, user_task: str, pattern: str, category: str) -> bool:
        """Check if the dangerous pattern is related to what the user asked for.

        Uses category-level keyword matching to check if the user's task
        explicitly mentions the type of dangerous operation being requested.

        Args:
            user_task: The declared task scope from the user.
            pattern: The regex pattern that matched.
            category: The category of danger (e.g., 'database_destructive').

        Returns:
            True if the operation type is explicitly in scope of the user's task.
        """
        task_lower = user_task.lower()

        # Category → keywords the user must mention to make pattern "in scope"
        category_keywords: dict[str, list[str]] = {
            "database_destructive": ["delete", "remove", "drop", "clean", "truncate", "purge", "clear"],
            "filesystem_destructive": ["delete", "remove", "clean", "wipe", "purge"],
            "code_execution": ["run", "execute", "eval", "script", "command"],
            "unexpected_network": ["send", "post", "upload", "submit", "request"],
            "privilege_escalation": ["admin", "root", "sudo", "privilege", "permission"],
        }

        keywords = category_keywords.get(category, [])
        return any(kw in task_lower for kw in keywords)


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
    Pass RuleBasedArmorIQClient() as the client for offline enforcement.

    Attributes:
        client: Optional client implementing ArmorIQClientProtocol.
                If None, adapter operates in stub mode.

    Example:
        >>> # Offline rule-based enforcement (no server)
        >>> armor = ArmorIQAdapter(client=RuleBasedArmorIQClient())
        >>> armor.enforce("book a flight", "SELECT * FROM flights")
        True
        >>> armor.enforce("book a flight", "DELETE FROM users")  # raises IntentViolationError
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        """Initialize the ArmorIQ intent enforcement adapter.

        Args:
            client: Optional client implementing ArmorIQClientProtocol —
                   must have is_action_aligned(user_task: str, action_plan: str) -> bool.
                   Pass RuleBasedArmorIQClient() for offline enforcement.
                   If None (default), adapter operates in stub mode (always allows).

        Example:
            >>> # Stub mode (always allow)
            >>> armor = ArmorIQAdapter()

            >>> # Offline rule-based enforcement
            >>> armor = ArmorIQAdapter(client=RuleBasedArmorIQClient())

            >>> # Server-backed enforcement
            >>> armor = ArmorIQAdapter(client=my_armoriq_api_client)
        """
        self.client = client
        mode = "enforcement" if client is not None else "stub"
        logger.info(f"Initialized ArmorIQAdapter in {mode} mode")

    def enforce(self, user_task: str, action_plan: str) -> bool:
        """Enforce that an action aligns with the user's declared task.

        Operates in two modes:
            1. **Stub mode** (client=None): Always returns True, logs the check.
            2. **Enforcement mode** (with client): Raises IntentViolationError if
               action does not align with the declared task.

        Args:
            user_task: The declared task scope or intent from the user.
            action_plan: The proposed action to execute.

        Returns:
            True if the action is aligned (or stub mode).

        Raises:
            IntentViolationError: If enforcement mode is active and action is misaligned.

        Example:
            >>> armor = ArmorIQAdapter(client=RuleBasedArmorIQClient())
            >>> armor.enforce("book a flight", "SELECT * FROM flights")
            True
            >>> try:
            ...     armor.enforce("book a flight", "DELETE FROM users")
            ... except IntentViolationError as e:
            ...     print(f"Blocked: {e.reason}")
        """
        logger.debug(f"Intent check: task='{user_task}', action='{action_plan[:50]}...'")

        # Stub mode: always allow, log the check
        if self.client is None:
            logger.debug("Stub mode: allowing action without enforcement")
            return True

        # Enforcement mode: check alignment with client
        try:
            is_aligned = self.client.is_action_aligned(user_task, action_plan)

            if not is_aligned:
                reason = f"Action does not align with task scope '{user_task}'"
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
