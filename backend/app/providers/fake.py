"""Deterministic offline fake providers for tests and demo mode."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterator

from app.domain import ChatMessage

_WORD_RE = re.compile(r"[a-z0-9]+")


class FakeLLM:
    """Deterministic offline LLM client."""

    def __init__(self) -> None:
        self.model = "fake-llm"

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
        json_object: bool = False,
    ) -> str:
        """Return safe empty JSON object when json_object=True, else echo user text."""
        _ = max_tokens
        if json_object:
            return "{}"
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break
        if not user_text and messages:
            user_text = messages[-1].get("content", "")
        snippet = " ".join(user_text.split())[:400]
        return f"[Demo mode echo] {snippet}" if snippet else "[Demo mode echo]"

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Yield a deterministic demo-mode response word by word citing [1] and [2]."""
        _ = (messages, max_tokens)
        words = [
            "In",
            "demo",
            "mode,",
            "based",
            "on",
            "passages",
            "[1]",
            "and",
            "[2],",
            "here",
            "is",
            "a",
            "deterministic",
            "offline",
            "answer.",
        ]
        for idx, word in enumerate(words):
            yield f"{word} " if idx < len(words) - 1 else word


class FakeEmbedder:
    """Deterministic hashing bag-of-words embedder."""

    def __init__(self, dimensions: int = 256) -> None:
        self.id = "fake-hash-256"
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Hash lowercase word tokens into buckets and L2-normalise each vector."""
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        tokens = _WORD_RE.findall(text.lower())
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
            bucket = int.from_bytes(digest, "little") % self.dimensions
            vec[bucket] += 1.0
        norm = math.sqrt(sum(val * val for val in vec))
        if norm > 0.0:
            vec = [val / norm for val in vec]
        return vec
