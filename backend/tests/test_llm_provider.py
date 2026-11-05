"""Tests for OpenAICompatibleLLM and OpenAIEmbedder using injected fake SDK clients."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from app.providers.embeddings import OpenAIEmbedder
from app.providers.llm import OpenAICompatibleLLM


@dataclass
class _FakeMessage:
    content: str | None


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeCompletionResponse:
    choices: list[_FakeChoice]


@dataclass
class _FakeDelta:
    content: str | None


@dataclass
class _FakeStreamChoice:
    delta: _FakeDelta


@dataclass
class _FakeStreamChunk:
    choices: list[_FakeStreamChoice]


@dataclass
class _FakeEmbeddingItem:
    index: int
    embedding: list[float]


@dataclass
class _FakeEmbeddingResponse:
    data: list[_FakeEmbeddingItem]


class _TransientServerError(Exception):
    status_code = 503


class _FakeChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failures_remaining = 0
        self.failure_exc: Exception = _TransientServerError("service unavailable")
        self.response_text = "completion answer"
        self.stream_deltas: list[str | None] = ["Hello ", None, "world!"]

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise self.failure_exc
        if kwargs.get("stream"):
            return self._iter_chunks()
        return _FakeCompletionResponse(
            choices=[_FakeChoice(message=_FakeMessage(content=self.response_text))]
        )

    def _iter_chunks(self) -> Iterator[_FakeStreamChunk]:
        yield _FakeStreamChunk(choices=[])
        for piece in self.stream_deltas:
            yield _FakeStreamChunk(choices=[_FakeStreamChoice(delta=_FakeDelta(content=piece))])


class _FakeEmbeddingsAPI:
    def __init__(self, dims: int = 4) -> None:
        self.dims = dims
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeEmbeddingResponse:
        self.calls.append(kwargs)
        batch: list[str] = kwargs["input"]
        items = [
            _FakeEmbeddingItem(index=idx, embedding=[float(idx)] * self.dims)
            for idx in range(len(batch))
        ]
        # Return reversed to verify index sorting
        return _FakeEmbeddingResponse(data=list(reversed(items)))


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.completions = _FakeChatCompletions()
        self.chat = type("ChatNS", (), {"completions": self.completions})()
        self.embeddings = _FakeEmbeddingsAPI()


def test_openai_kwargs_no_temperature_and_reasoning_effort() -> None:
    fake_client = _FakeOpenAIClient()
    llm = OpenAICompatibleLLM(
        api_key="test-key",
        model="gpt-6-luna",
        base_url=None,
        reasoning_effort="medium",
        client=fake_client,
        backoff_base=0.0,
    )

    out = llm.complete(
        [{"role": "user", "content": "Summarize"}],
        max_tokens=512,
        json_object=True,
    )
    assert out == "completion answer"
    assert len(fake_client.completions.calls) == 1
    sent = fake_client.completions.calls[0]

    assert "temperature" not in sent
    assert sent["model"] == "gpt-6-luna"
    assert sent["reasoning_effort"] == "medium"
    assert "extra_body" not in sent
    assert sent["max_completion_tokens"] == 512
    assert sent["response_format"] == {"type": "json_object"}
    assert "stream" not in sent


def test_openrouter_kwargs_uses_extra_body_and_omits_reasoning_effort() -> None:
    fake_client = _FakeOpenAIClient()
    llm = OpenAICompatibleLLM(
        api_key="or-key",
        model="openai/gpt-6-luna",
        base_url="https://openrouter.ai/api/v1",
        reasoning_effort="high",
        client=fake_client,
        backoff_base=0.0,
    )

    llm.complete([{"role": "user", "content": "Ping"}], json_object=False)
    sent = fake_client.completions.calls[0]

    assert "temperature" not in sent
    assert "reasoning_effort" not in sent
    assert sent["extra_body"] == {"reasoning": {"effort": "high"}}
    assert "response_format" not in sent
    assert "max_completion_tokens" not in sent


def test_stream_yields_deltas_and_retries_transient_errors() -> None:
    fake_client = _FakeOpenAIClient()
    fake_client.completions.failures_remaining = 2
    llm = OpenAICompatibleLLM(
        api_key="test-key",
        model="gpt-6-luna",
        client=fake_client,
        backoff_base=0.0,
    )

    chunks = list(llm.stream([{"role": "user", "content": "Stream test"}], max_tokens=100))
    assert chunks == ["Hello ", "world!"]
    assert len(fake_client.completions.calls) == 3
    assert fake_client.completions.calls[-1]["stream"] is True
    assert "temperature" not in fake_client.completions.calls[-1]


def test_non_transient_error_is_not_retried() -> None:
    fake_client = _FakeOpenAIClient()
    fake_client.completions.failures_remaining = 2
    fake_client.completions.failure_exc = ValueError("bad request payload")
    llm = OpenAICompatibleLLM(
        api_key="test-key",
        model="gpt-6-luna",
        client=fake_client,
        backoff_base=0.0,
    )

    with pytest.raises(ValueError, match="bad request payload"):
        llm.complete([{"role": "user", "content": "Fail fast"}])
    assert len(fake_client.completions.calls) == 1


def test_openai_embedder_batches_256_and_sets_dimensions() -> None:
    fake_client = _FakeOpenAIClient()
    small = OpenAIEmbedder(
        api_key="test-key",
        model="text-embedding-3-small",
        client=fake_client,
        backoff_base=0.0,
    )
    large = OpenAIEmbedder(
        api_key="test-key",
        model="text-embedding-3-large",
        client=fake_client,
        backoff_base=0.0,
    )

    assert small.id == "text-embedding-3-small"
    assert small.dimensions == 1536
    assert large.dimensions == 3072

    texts = [f"passage {i}" for i in range(300)]
    vectors = small.embed(texts)
    assert len(vectors) == 300
    assert len(fake_client.embeddings.calls) == 2
    assert len(fake_client.embeddings.calls[0]["input"]) == 256
    assert len(fake_client.embeddings.calls[1]["input"]) == 44
    assert vectors[0] == [0.0, 0.0, 0.0, 0.0]
    assert vectors[1] == [1.0, 1.0, 1.0, 1.0]
