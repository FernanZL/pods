"""OpenAI-compatible chat completion provider (OpenAI and OpenRouter)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from app.domain import ChatMessage


def is_transient_error(exc: Exception) -> bool:
    """Return True if an SDK or network error is transient and worth retrying."""
    if isinstance(
        exc,
        (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return True
    if isinstance(exc, APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


class OpenAICompatibleLLM:
    """Chat completions wrapper supporting OpenAI and OpenRouter endpoints."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        reasoning_effort: str | None = "low",
        client: Any = None,
        backoff_base: float = 0.2,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.reasoning_effort = reasoning_effort
        self._backoff_base = backoff_base
        if client is not None:
            self._client = client
        else:
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url is not None:
                client_kwargs["base_url"] = base_url
            self._client = OpenAI(**client_kwargs)

    def _build_kwargs(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        json_object: bool = False,
        stream: bool = False,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if self.reasoning_effort is not None:
            if self.base_url is None:
                kwargs["reasoning_effort"] = self.reasoning_effort
            else:
                kwargs["extra_body"] = {"reasoning": {"effort": self.reasoning_effort}}
        if json_object:
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            kwargs["stream"] = True
        return kwargs

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        json_object: bool = False,
    ) -> str:
        """Run a single non-streamed chat completion with transient retries."""
        kwargs = self._build_kwargs(
            messages,
            max_tokens=max_tokens,
            json_object=json_object,
            stream=False,
        )
        max_tries = 3
        for attempt in range(max_tries):
            try:
                response = self._client.chat.completions.create(**kwargs)
                choices = getattr(response, "choices", None)
                if not choices:
                    return ""
                return choices[0].message.content or ""
            except Exception as exc:
                if attempt >= max_tries - 1 or not is_transient_error(exc):
                    raise
                time.sleep(self._backoff_base * (2**attempt))
        return ""

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Stream text delta pieces from chat completions with transient retries."""
        kwargs = self._build_kwargs(messages, max_tokens=max_tokens, stream=True)
        max_tries = 3
        for attempt in range(max_tries):
            yielded = False
            try:
                response = self._client.chat.completions.create(**kwargs)
                for chunk in response:
                    choices = getattr(chunk, "choices", None)
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    content = getattr(delta, "content", None) if delta is not None else None
                    if content:
                        yielded = True
                        yield content
                return
            except Exception as exc:
                if yielded or attempt >= max_tries - 1 or not is_transient_error(exc):
                    raise
                time.sleep(self._backoff_base * (2**attempt))
