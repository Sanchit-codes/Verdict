"""Gemini LLM integration for HallucinationGuard Flask backend.

This module provides a simple wrapper around Google's Gemini API
for text generation, designed to work seamlessly with the validation pipeline.
"""

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class GeminiGenerator:
    """Wrapper for Google Gemini API with error handling and latency tracking.

    This class manages Gemini text generation requests and provides
    transparent latency measurement for pipeline integration.
    """

    def __init__(self, model: str = "gemini-2.5-flash"):
        """Initialize GeminiGenerator with a specific model.

        Args:
            model: Gemini model identifier (e.g., "gemini-2.5-flash").
                   Defaults to "gemini-2.5-flash" as per SDK guidance.

        Raises:
            ImportError: If google.generativeai library is not installed.
            ValueError: If GOOGLE_API_KEY environment variable is not set.
        """
        try:
            import google.generativeai as genai
        except ImportError as e:
            logger.error(
                "google.generativeai not installed. "
                "Install with: pip install google-generativeai"
            )
            raise ImportError(
                "google.generativeai library required for GeminiGenerator"
            ) from e

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY environment variable not set")
            raise ValueError("GOOGLE_API_KEY environment variable must be set")

        self.model_name = model
        self.genai = genai

        try:
            self.genai.configure(api_key=api_key)
            logger.info(f"GeminiGenerator initialized with model={model}")
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}")
            raise ValueError(f"Failed to configure Gemini API: {e}") from e

    def generate(
        self,
        prompt: str,
        context: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Generate text using Gemini.

        Args:
            prompt: User query or instruction for generation.
            context: Optional reference context (e.g., retrieved documents).
                     Prepended to prompt to provide grounding.
            temperature: Sampling temperature (0.0 to 2.0).
                         Defaults to 0.7 for balanced creativity.
            max_tokens: Maximum output tokens. Defaults to 1024.

        Returns:
            Dictionary with keys:
                - generated_text: The generated response text
                - latency_ms: Generation time in milliseconds
                - model: Model name used
                - error: None if successful, error message otherwise

        Example:
            >>> generator = GeminiGenerator()
            >>> result = generator.generate(
            ...     prompt="What is the capital of France?",
            ...     context="France is a European country."
            ... )
            >>> if result['error'] is None:
            ...     print(f"Generated: {result['generated_text']}")
            ...     print(f"Latency: {result['latency_ms']:.1f}ms")
        """
        if not prompt or not isinstance(prompt, str):
            logger.error(f"Invalid prompt: {type(prompt)}")
            return {
                "generated_text": "",
                "latency_ms": 0.0,
                "model": self.model_name,
                "error": "Prompt must be a non-empty string",
            }

        # Build full prompt with optional context
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nQuery:\n{prompt}"

        start_time = time.time()

        try:
            # Create the model instance
            model = self.genai.GenerativeModel(self.model_name)

            # Generate content
            response = model.generate_content(
                full_prompt,
                generation_config=self.genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )

            # Extract text from response
            if response.text:
                generated_text = response.text.strip()
            else:
                generated_text = ""
                logger.warning("Gemini returned empty response")

            latency_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Generation successful: {len(generated_text)} chars, "
                f"latency={latency_ms:.1f}ms"
            )

            return {
                "generated_text": generated_text,
                "latency_ms": latency_ms,
                "model": self.model_name,
                "error": None,
            }

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            # Log appropriately based on error type
            if "API" in str(type(e).__name__) or "quota" in error_msg.lower():
                logger.warning(f"Gemini API error: {error_msg}")
            else:
                logger.error(f"Generation error: {e}", exc_info=True)

            return {
                "generated_text": "",
                "latency_ms": latency_ms,
                "model": self.model_name,
                "error": error_msg,
            }

    def is_available(self) -> bool:
        """Check if Gemini API is available.

        Returns:
            True if the API key is configured and valid, False otherwise.
        """
        api_key = os.getenv("GOOGLE_API_KEY")
        return bool(api_key)
