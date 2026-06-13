"""
LLMClient
=========
Single responsibility: make one LLM call with exponential-backoff retry.

* Only class that imports the Gemini SDK.
* Swap backend by subclassing or replacing at construction time.
* Raises LLMError after all retries are exhausted.
"""

from __future__ import annotations

import os
import random
import time


class LLMError(RuntimeError):
    """Raised when the LLM call fails after all retries."""


class LLMClient:
    """
    Wraps the Gemini Flash API with retry logic.

    Parameters
    ----------
    api_key      : Gemini API key. Falls back to GEMINI_API_KEY env var.
    model_name   : Gemini model to use.
    max_retries  : Number of attempts before raising LLMError.
    backoff_base : Base for exponential backoff (seconds).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
        max_retries: int = 3,
        backoff_base: float = 2.0,
    ):
        self.model_name   = model_name
        self.max_retries  = max_retries
        self.backoff_base = backoff_base

        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if resolved_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=resolved_key)
                self._genai = genai
            except ImportError:
                self._genai = None
        else:
            self._genai = None

    # ── Public interface ──────────────────────────────────────────────────────

    def call(self, prompt: str, *, expect_json: bool = False) -> str:
        """
        Send *prompt* to the LLM and return the text response.

        Parameters
        ----------
        prompt      : The prompt string.
        expect_json : If True, appends an instruction to return valid JSON only.

        Raises
        ------
        LLMError : If all retries fail.
        """
        if expect_json:
            prompt = prompt + "\n\nRespond with valid JSON only. No markdown, no code fences."

        return self._with_retry(prompt)

    # ── Private ───────────────────────────────────────────────────────────────

    def _with_retry(self, prompt: str) -> str:
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return self._invoke(prompt)
            except Exception as exc:
                last_exc = exc
                wait = self.backoff_base ** attempt + random.uniform(0, 1)
                time.sleep(wait)

        raise LLMError(
            f"LLM call failed after {self.max_retries} retries: {last_exc}"
        ) from last_exc

    def _invoke(self, prompt: str) -> str:
        if self._genai is None:
            raise LLMError("No LLM backend configured (missing API key or SDK).")
        model    = self._genai.GenerativeModel(self.model_name)
        response = model.generate_content(prompt)
        return response.text.strip()
