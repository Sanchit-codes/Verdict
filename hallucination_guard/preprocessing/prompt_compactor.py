"""Extractive prompt/context compaction for HallucinationGuard preprocessing.

Reduces large contexts to fit within a token budget by ranking sentences
by relevance to the prompt and selecting the top-k.  Reuses the
``all-MiniLM-L6-v2`` embedding model already loaded by ``EmbeddingValidator``
— no additional model downloads.

Falls back to simple head-truncation when the embedding model is unavailable.

Usage::

    compactor = PromptCompactor()
    result = compactor.compact(
        context="Very long document text...",
        prompt="What is insulin?",
        max_tokens=512,
    )
    print(result.compacted_text)
    print(result.compression_ratio)
"""

import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Rough estimate: 4 chars ≈ 1 token
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving non-empty ones."""
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


class CompactionResult(BaseModel):
    """Result from context compaction.

    Attributes:
        original_text: Full unmodified context.
        compacted_text: Compacted context (subset of sentences or truncated).
        original_token_estimate: Estimated token count before compaction.
        compacted_token_estimate: Estimated token count after compaction.
        compression_ratio: compacted_tokens / original_tokens in [0, 1].
        strategy: ``"embedding"`` for relevance-based, ``"truncation"`` for fallback.
    """

    original_text: str
    compacted_text: str
    original_token_estimate: int = Field(ge=0)
    compacted_token_estimate: int = Field(ge=0)
    compression_ratio: float = Field(ge=0.0, le=1.0)
    strategy: Literal["embedding", "truncation"]

    model_config = {"frozen": True}


class PromptCompactor:
    """Extractive context compactor.

    Scores each sentence in the context by cosine similarity to the
    prompt embedding and greedily selects sentences (highest-score first)
    until the token budget is exhausted.  Preserves sentence order in
    the output so the compacted context reads naturally.

    The embedding model is loaded lazily on first use and relies on the
    same singleton cache as ``EmbeddingValidator``.

    If the embedding model is not available or raises any error, the
    compactor falls back to simple head-truncation (first N tokens).
    """

    def compact(
        self,
        context: str,
        prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> CompactionResult:
        """Compact a context string to fit within ``max_tokens``.

        Args:
            context: The full context text to compact.
            prompt: Optional prompt to guide sentence relevance scoring.
                    When ``None``, sentences are selected by their position
                    (head selection).
            max_tokens: Maximum target token count for the output.

        Returns:
            ``CompactionResult`` with compacted text and metadata.
        """
        if not context or not context.strip():
            return CompactionResult(
                original_text=context,
                compacted_text=context,
                original_token_estimate=0,
                compacted_token_estimate=0,
                compression_ratio=1.0,
                strategy="truncation",
            )

        original_tokens = _estimate_tokens(context)

        # Already within budget — return as-is
        if original_tokens <= max_tokens:
            return CompactionResult(
                original_text=context,
                compacted_text=context,
                original_token_estimate=original_tokens,
                compacted_token_estimate=original_tokens,
                compression_ratio=1.0,
                strategy="embedding",
            )

        sentences = _split_sentences(context)
        if not sentences:
            return self._truncate(context, original_tokens, max_tokens)

        # Try embedding-based compaction first
        if prompt:
            try:
                return self._compact_with_embeddings(
                    context, sentences, prompt, original_tokens, max_tokens
                )
            except Exception as e:
                logger.warning(
                    f"PromptCompactor: embedding compaction failed ({e}), "
                    f"falling back to truncation"
                )

        # Fallback: head selection (keep first N sentences within budget)
        return self._compact_head(context, sentences, original_tokens, max_tokens)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compact_with_embeddings(
        self,
        original_text: str,
        sentences: list[str],
        prompt: str,
        original_tokens: int,
        max_tokens: int,
    ) -> CompactionResult:
        """Embedding-based extractive compaction."""
        import numpy as np
        from hallucination_guard.validators.embedding import EmbeddingValidator

        # Use the cached embedding model
        validator = EmbeddingValidator({"threshold": 0.5, "timeout_ms": 600})
        if not validator.is_available():
            raise RuntimeError("Embedding model not available")

        model = validator._model  # type: ignore[attr-defined]

        # Encode prompt and all sentences
        all_texts = [prompt] + sentences
        embeddings = model.encode(all_texts, convert_to_numpy=True, normalize_embeddings=True)

        prompt_emb = embeddings[0]
        sentence_embs = embeddings[1:]

        # Score each sentence: cosine sim (normalized → dot product)
        scores = np.dot(sentence_embs, prompt_emb)  # shape: (N,)

        # Greedy selection in score order, but preserve original sentence ordering
        ranked_indices = list(np.argsort(scores)[::-1])
        selected: list[int] = []
        budget = max_tokens

        for idx in ranked_indices:
            s_tokens = _estimate_tokens(sentences[idx])
            if s_tokens <= budget:
                selected.append(idx)
                budget -= s_tokens
            if budget <= 0:
                break

        # Re-sort selected indices to preserve original order
        selected.sort()
        compacted = " ".join(sentences[i] for i in selected)
        compacted_tokens = _estimate_tokens(compacted)

        ratio = compacted_tokens / original_tokens if original_tokens > 0 else 1.0
        ratio = min(1.0, max(0.0, ratio))

        return CompactionResult(
            original_text=original_text,
            compacted_text=compacted,
            original_token_estimate=original_tokens,
            compacted_token_estimate=compacted_tokens,
            compression_ratio=ratio,
            strategy="embedding",
        )

    def _compact_head(
        self,
        original_text: str,
        sentences: list[str],
        original_tokens: int,
        max_tokens: int,
    ) -> CompactionResult:
        """Head selection: take sentences from the top until budget is met."""
        selected: list[str] = []
        budget = max_tokens

        for sentence in sentences:
            s_tokens = _estimate_tokens(sentence)
            if s_tokens <= budget:
                selected.append(sentence)
                budget -= s_tokens
            if budget <= 0:
                break

        compacted = " ".join(selected)
        compacted_tokens = _estimate_tokens(compacted)
        ratio = compacted_tokens / original_tokens if original_tokens > 0 else 1.0
        ratio = min(1.0, max(0.0, ratio))

        return CompactionResult(
            original_text=original_text,
            compacted_text=compacted,
            original_token_estimate=original_tokens,
            compacted_token_estimate=compacted_tokens,
            compression_ratio=ratio,
            strategy="truncation",
        )

    def _truncate(
        self,
        text: str,
        original_tokens: int,
        max_tokens: int,
    ) -> CompactionResult:
        """Hard character truncation as last resort."""
        max_chars = max_tokens * _CHARS_PER_TOKEN
        compacted = text[:max_chars]
        compacted_tokens = _estimate_tokens(compacted)
        ratio = compacted_tokens / original_tokens if original_tokens > 0 else 1.0
        ratio = min(1.0, max(0.0, ratio))

        return CompactionResult(
            original_text=text,
            compacted_text=compacted,
            original_token_estimate=original_tokens,
            compacted_token_estimate=compacted_tokens,
            compression_ratio=ratio,
            strategy="truncation",
        )
