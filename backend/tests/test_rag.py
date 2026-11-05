"""Tests for RAG retrieval, scope filtering, SSE event order, and message persistence."""

from __future__ import annotations

import pytest

from app import db, storage
from app.domain import Segment, Transcript
from app.models import Episode, Podcast, utcnow
from app.schemas import ChatRequest, Scope
from app.services import conversations, indexing, rag


def _create_podcast_and_episode(
    *,
    pod_title: str,
    rss_url: str,
    ep_guid: str,
    ep_title: str,
    speakers: dict[str, str],
    segments: list[Segment],
) -> tuple[int, int]:
    now = utcnow()
    with db.session_scope() as session:
        podcast = Podcast(
            title=pod_title,
            rss_url=rss_url,
            slug=storage.slugify(pod_title),
        )
        session.add(podcast)
        session.flush()
        assert podcast.id is not None

        ep = Episode(
            podcast_id=podcast.id,
            guid=ep_guid,
            number=1,
            title=ep_title,
            slug=storage.episode_slug(1, ep_title),
            audio_url=f"{rss_url}/{ep_guid}.mp3",
            duration_seconds=300,
            downloaded_at=now,
            transcribed_at=now,
            speakers=speakers,
        )
        session.add(ep)
        session.flush()
        assert ep.id is not None

        t_path = storage.episode_dir(podcast, ep) / "transcript.json"
        storage.write_transcript(
            t_path,
            Transcript(
                episode_id=ep.id,
                model="fake",
                speakers=speakers,
                segments=segments,
            ),
        )
        ep.transcript_path = storage.to_rel(t_path)
        session.add(ep)
        session.commit()
        pod_id, ep_id = podcast.id, ep.id

    indexing.index_episode(ep_id)
    return pod_id, ep_id


def test_empty_index_answers_without_llm_call(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbid_llm():  # noqa: ANN202
        raise AssertionError("get_llm() must not be called when the index is empty")

    monkeypatch.setattr(rag, "get_llm", _forbid_llm)

    events = list(rag.answer_stream(ChatRequest(message="What about sleep?")))
    names = [ev["event"] for ev in events]
    assert names == ["meta", "citations", "token", "done"]

    assert events[1]["data"]["citations"] == []
    token_text = events[2]["data"]["text"]
    assert "empty" in token_text.lower()
    assert "library" in token_text.lower()
    assert events[3]["data"]["citations"] == []

    conv_id = events[0]["data"]["conversation_id"]
    conv = conversations.get_conversation(conv_id)
    assert conv is not None
    detail = conversations.to_detail(conv)
    assert len(detail.messages) == 2
    assert detail.messages[0].role == "user"
    assert detail.messages[1].role == "assistant"
    assert detail.messages[1].content == token_text


def test_rag_event_order_citations_and_persistence() -> None:
    _, sleep_ep_id = _create_podcast_and_episode(
        pod_title="Sleep Cast",
        rss_url="demo://sleep-cast",
        ep_guid="sleep-1",
        ep_title="Circadian Light & Melatonin",
        speakers={"A": "Dr. Fictional Host", "B": "Prof. Demo Guest"},
        segments=[
            Segment(
                "A",
                0.0,
                15.0,
                "Morning sunlight calibrates circadian rhythm and evening melatonin.",
            ),
            Segment(
                "B",
                16.0,
                35.0,
                "Avoiding late afternoon caffeine preserves deep slow-wave sleep pressure.",
            ),
        ],
    )

    events = list(rag.answer_stream(ChatRequest(message="How does morning sunlight affect sleep?")))
    assert events[0]["event"] == "meta"
    assert events[1]["event"] == "citations"
    assert events[-1]["event"] == "done"

    token_events = events[2:-1]
    assert len(token_events) >= 3
    assert all(ev["event"] == "token" for ev in token_events)

    cand_citations = events[1]["data"]["citations"]
    assert len(cand_citations) >= 1
    assert cand_citations[0]["episode_id"] == sleep_ep_id
    assert cand_citations[0]["speaker"] in ("Dr. Fictional Host", "Prof. Demo Guest")
    assert len(cand_citations[0]["snippet"]) <= 300

    done_citations = events[-1]["data"]["citations"]
    assert len(done_citations) >= 1

    conv_id = events[0]["data"]["conversation_id"]
    # Follow-up turn triggers query condensation over history
    followup_events = list(
        rag.answer_stream(
            ChatRequest(conversation_id=conv_id, message="What about caffeine timing?")
        )
    )
    assert followup_events[0]["event"] == "meta"
    assert followup_events[-1]["event"] == "done"

    conv = conversations.get_conversation(conv_id)
    assert conv is not None
    detail = conversations.to_detail(conv)
    assert detail.message_count == 4
    assert [m.role for m in detail.messages] == ["user", "assistant", "user", "assistant"]
    assert len(detail.messages[1].citations) >= 1


def test_rag_scope_filters_restrict_citations_to_scoped_episodes_and_podcasts() -> None:
    pod1_id, ep1_id = _create_podcast_and_episode(
        pod_title="Podcast Alpha",
        rss_url="demo://alpha",
        ep_guid="alpha-1",
        ep_title="Alpha Sleep Episode",
        speakers={"A": "Host", "B": "Guest"},
        segments=[
            Segment(
                "B",
                0.0,
                20.0,
                "Sleep circadian rhythm melatonin morning sunlight protocol.",
            )
        ],
    )
    pod2_id, ep2_id = _create_podcast_and_episode(
        pod_title="Podcast Beta",
        rss_url="demo://beta",
        ep_guid="beta-1",
        ep_title="Beta Exercise Episode",
        speakers={"A": "Host", "B": "Guest"},
        segments=[
            Segment(
                "B",
                0.0,
                20.0,
                "Zone two endurance resistance training muscle hypertrophy.",
            )
        ],
    )
    assert pod1_id != pod2_id

    # Query mentions sleep words, yet scoping to ep2_id must ONLY cite ep2_id!
    scoped_ep_events = list(
        rag.answer_stream(
            ChatRequest(
                message="sleep circadian rhythm melatonin",
                scope=Scope(episode_ids=[ep2_id]),
            )
        )
    )
    ep_cits = scoped_ep_events[1]["data"]["citations"]
    assert len(ep_cits) >= 1
    assert {c["episode_id"] for c in ep_cits} == {ep2_id}
    assert {c["episode_id"] for c in scoped_ep_events[-1]["data"]["citations"]} == {ep2_id}

    # Scoping to pod1_id must ONLY cite ep1_id!
    scoped_pod_events = list(
        rag.answer_stream(
            ChatRequest(
                message="resistance training hypertrophy",
                scope=Scope(podcast_ids=[pod1_id]),
            )
        )
    )
    pod_cits = scoped_pod_events[1]["data"]["citations"]
    assert len(pod_cits) >= 1
    assert {c["episode_id"] for c in pod_cits} == {ep1_id}
