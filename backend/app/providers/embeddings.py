"""OpenAI embeddings provider."""

from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from app.providers.llm import is_transient_error

_BATCH_SIZE = 256


class OpenAIEmbedder:
    """Batch text embedder backed by the OpenAI embeddings endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        client: Any = None,
        backoff_base: float = 0.2,
    ) -> None:
        self.id = model
        self.model = model
        self.dimensions = 3072 if "-large" in model else 1536
        self._backoff_base = backoff_base
        self._client = client if client is not None else OpenAI(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches of up to 256 items."""
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = [t if t else " " for t in texts[start : start + _BATCH_SIZE]]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        max_tries = 3
        for attempt in range(max_tries):
            try:
                response = self._client.embeddings.create(model=self.model, input=batch)
                ordered = sorted(
                    response.data,
                    key=lambda item: getattr(item, "index", 0),
                )
                return [list(item.embedding) for item in ordered]
            except Exception as exc:
                if attempt >= max_tries - 1 or not is_transient_error(exc):
                    raise
                time.sleep(self._backoff_base * (2**attempt))
        return []
