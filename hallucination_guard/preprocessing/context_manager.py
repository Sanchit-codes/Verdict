"""In-memory context manager for HallucinationGuard preprocessing.

Stores, retrieves, and dynamically updates context entries keyed by a
session/domain key.  All state lives in-process — no filesystem or network
dependency — satisfying the zero-infrastructure principle.

Typical usage::

    mgr = ContextManager()
    mgr.store("medical", "Diabetes is a chronic condition...")
    mgr.update("medical", "Insulin is the primary treatment.")
    ctx = mgr.retrieve("medical")  # merged context
    mgr.compact("medical", prompt="What is insulin?")  # reduce token count
"""

import logging
import time
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Rough estimate: average English word ≈ 1.3 tokens
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate based on character count."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


class ContextEntry(BaseModel):
    """Immutable snapshot of a stored context entry.

    Attributes:
        key: The session/domain key this entry belongs to.
        content: The full context text (possibly compacted).
        token_count: Approximate token count for the content.
        created_at: Unix timestamp when the entry was first created.
        updated_at: Unix timestamp of the last update.
        compacted: Whether the content has been compacted.
    """

    key: str
    content: str
    token_count: int = Field(ge=0)
    created_at: float
    updated_at: float
    compacted: bool = False

    model_config = {"frozen": True}


class ContextManager:
    """In-memory context store with dynamic update support.

    Manages a dict of ``key → ContextEntry`` in process memory.
    Entries can grow dynamically as new context arrives; call
    ``compact()`` when the entry grows beyond a token budget.

    Thread safety: Not thread-safe by default. For concurrent use,
    wrap calls with an external lock.

    Example::

        mgr = ContextManager()
        mgr.store("session_1", "France is a country in Europe.")
        mgr.update("session_1", "Its capital is Paris.")
        print(mgr.retrieve("session_1"))
        # France is a country in Europe.
        # Its capital is Paris.
    """

    def __init__(self) -> None:
        self._store: dict[str, ContextEntry] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, key: str, context: str) -> ContextEntry:
        """Store a context entry, replacing any existing entry for this key.

        Args:
            key: Session/domain key (e.g. ``"session_1"``, ``"medical"``).
            context: Context text to store.

        Returns:
            The created ``ContextEntry``.
        """
        now = time.time()
        entry = ContextEntry(
            key=key,
            content=context,
            token_count=_estimate_tokens(context),
            created_at=now,
            updated_at=now,
        )
        self._store[key] = entry
        logger.debug(
            f"ContextManager: stored '{key}' ({entry.token_count} tokens)"
        )
        return entry

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve stored context for a key.

        Args:
            key: Session/domain key.

        Returns:
            Context text if found, or ``None``.
        """
        entry = self._store.get(key)
        return entry.content if entry is not None else None

    def retrieve_entry(self, key: str) -> Optional[ContextEntry]:
        """Retrieve the full ``ContextEntry`` for a key.

        Args:
            key: Session/domain key.

        Returns:
            ``ContextEntry`` if found, or ``None``.
        """
        return self._store.get(key)

    def update(self, key: str, new_context: str, separator: str = "\n") -> ContextEntry:
        """Append new context to an existing entry.

        If no entry exists for ``key``, creates a new one.

        Args:
            key: Session/domain key.
            new_context: Additional context text to append.
            separator: Separator between old and new context. Default ``"\\n"``.

        Returns:
            Updated ``ContextEntry``.
        """
        existing = self._store.get(key)
        if existing is None:
            return self.store(key, new_context)

        merged = existing.content + separator + new_context
        now = time.time()
        updated = ContextEntry(
            key=key,
            content=merged,
            token_count=_estimate_tokens(merged),
            created_at=existing.created_at,
            updated_at=now,
            compacted=False,  # merged content is no longer compacted
        )
        self._store[key] = updated
        logger.debug(
            f"ContextManager: updated '{key}' "
            f"({existing.token_count} → {updated.token_count} tokens)"
        )
        return updated

    def compact(
        self,
        key: str,
        prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> Optional[ContextEntry]:
        """Compact the stored context for a key using ``PromptCompactor``.

        Runs extractive compaction on the stored content and replaces
        the entry with the compacted version.

        Args:
            key: Session/domain key.
            prompt: Optional prompt to guide relevance-based selection.
            max_tokens: Target maximum token count after compaction.

        Returns:
            Updated ``ContextEntry`` with compacted content, or ``None``
            if no entry exists.
        """
        entry = self._store.get(key)
        if entry is None:
            logger.debug(f"ContextManager: compact called on missing key '{key}'")
            return None

        # Import here to avoid circular imports at module level
        from hallucination_guard.preprocessing.prompt_compactor import PromptCompactor

        compactor = PromptCompactor()
        result = compactor.compact(
            context=entry.content,
            prompt=prompt,
            max_tokens=max_tokens,
        )

        now = time.time()
        compacted_entry = ContextEntry(
            key=key,
            content=result.compacted_text,
            token_count=result.compacted_token_estimate,
            created_at=entry.created_at,
            updated_at=now,
            compacted=True,
        )
        self._store[key] = compacted_entry
        logger.debug(
            f"ContextManager: compacted '{key}' "
            f"({entry.token_count} → {compacted_entry.token_count} tokens, "
            f"ratio={result.compression_ratio:.2f})"
        )
        return compacted_entry

    def clear(self, key: str) -> bool:
        """Remove a specific entry.

        Args:
            key: Session/domain key to remove.

        Returns:
            ``True`` if an entry was removed, ``False`` if key not found.
        """
        existed = key in self._store
        self._store.pop(key, None)
        if existed:
            logger.debug(f"ContextManager: cleared '{key}'")
        return existed

    def clear_all(self) -> int:
        """Remove all stored entries.

        Returns:
            Number of entries removed.
        """
        count = len(self._store)
        self._store.clear()
        logger.debug(f"ContextManager: cleared all ({count} entries)")
        return count

    def keys(self) -> list[str]:
        """Return all stored keys."""
        return list(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)
