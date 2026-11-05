"""Tests for deterministic offline FakeLLM and FakeEmbedder."""

from __future__ import annotations

import json
import math

from app.domain import Embedder, LLMClient
from app.providers.fake import FakeEmbedder, FakeLLM


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_llm_protocol_and_json_mode() -> None:
    llm = FakeLLM()
    assert isinstance(llm, LLMClient)
    assert llm.model == "fake-llm"

    msgs = [{"role": "user", "content": "Identify the speakers"}]
    raw = llm.complete(msgs, json_object=True)
    assert json.loads(raw) == {}
    assert llm.complete(msgs, json_object=True) == raw


def test_fake_llm_complete_echo_and_stream() -> None:
    llm = FakeLLM()
    msgs = [{"role": "user", "content": "circadian melatonin timing"}]

    echo1 = llm.complete(msgs)
    echo2 = llm.complete(msgs)
    assert echo1 == echo2
    assert "circadian melatonin timing" in echo1

    pieces = list(llm.stream(msgs))
    assert len(pieces) > 5
    joined = "".join(pieces)
    assert "[1]" in joined
    assert "[2]" in joined
    assert "demo mode" in joined.lower()
    assert "".join(llm.stream(msgs)) == joined


def test_fake_embedder_normalization_and_lexical_similarity() -> None:
    emb = FakeEmbedder(dimensions=256)
    assert isinstance(emb, Embedder)
    assert emb.id == "fake-hash-256"
    assert emb.dimensions == 256
    assert emb.embed([]) == []

    empty_vec = emb.embed([""])[0]
    assert len(empty_vec) == 256
    assert all(v == 0.0 for v in empty_vec)

    texts = [
        "Morning sunlight anchors circadian rhythm and melatonin sleep timing.",
        "Circadian rhythm and evening melatonin regulate restorative sleep.",
        "Heavy resistance training and progressive overload build muscle strength.",
    ]
    v_sleep_a, v_sleep_b, v_lift = emb.embed(texts)

    for vec in (v_sleep_a, v_sleep_b, v_lift):
        norm = math.sqrt(sum(x * x for x in vec))
        assert math.isclose(norm, 1.0, rel_tol=1e-6)

    # Case-insensitive and deterministic
    assert emb.embed([texts[0].upper()])[0] == v_sleep_a

    sim_related = _cosine(v_sleep_a, v_sleep_b)
    sim_unrelated = _cosine(v_sleep_a, v_lift)
    assert sim_related > sim_unrelated
    assert sim_related > 0.35
