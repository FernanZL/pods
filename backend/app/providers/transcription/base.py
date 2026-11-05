"""Shared helpers for transcription provider implementations."""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from openai import (
    APIError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)

_MIME_BY_SUFFIX: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}

_NON_RETRYABLE = (
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)

_RETRYABLE = (
    APIError,
    httpx.HTTPError,
    ConnectionError,
    TimeoutError,
    RuntimeError,
)


def encode_audio_data_url(path: Path) -> str:
    """Encode an audio file as a base64 data URL (e.g. data:audio/mpeg;base64,...)."""
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "audio/mpeg")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def get_field(obj: Any, name: str, default: Any = None) -> Any:
    """Read an attribute or dict key uniformly across SDK models and test fakes."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def with_retry[T](
    fn: Callable[[], T],
    *,
    tries: int = 3,
    base_delay: float = 1.0,
    sleep_fn: Callable[[float], None] | None = None,
) -> T:
    """Execute fn with exponential backoff (default 3 attempts) on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max(1, tries)):
        try:
            return fn()
        except _NON_RETRYABLE:
            raise
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt + 1 >= tries:
                raise
            (sleep_fn or time.sleep)(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc
