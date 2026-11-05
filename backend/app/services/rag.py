"""Retrieval-augmented generation (RAG) streaming chat service."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Literal

from sqlmodel import col, select

from app import db, storage
from app.config import get_settings
from app.domain import ChatMessage, ScoredPassage
from app.models import Episode, Message
from app.providers import get_embedder, get_llm
from app.schemas import ChatRequest, Citation, ConversationPatch, Scope
from app.services import conversations
from app.services.vectorstore import get_vector_store

_CITATION_MARKER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")

CONDENSE_SYSTEM_PROMPT = (
    "Given the prior conversation and a follow-up user message, rewrite the follow-up "
    "message into a concise, standalone search query suitable for semantic retrieval over "
    "podcast transcripts. Output only the standalone search query."
)

RAG_SYSTEM_PROMPT = (
    "You are a knowledgeable podcast research assistant. Answer the user's question ONLY "
    "using the numbered podcast passages provided below. Cite supporting passages inline "
    "using bracketed numbers such as [1] or [2]. If the provided passages do not cover "
    "the question, explicitly say that the indexed podcast library does not cover it."
)

EMPTY_LIBRARY_MESSAGE = (
    "Your podcast library index is currently empty. Add a podcast and process episodes "
    "in Library to start chatting over transcripts."
)


def build_scope_filter(scope: Scope) -> dict[str, Any] | None:
    """Build a ChromaDB ``where`` filter from ``Scope``."""
    clauses: list[dict[str, Any]] = []
    if scope.podcast_ids:
        clauses.append({"podcast_id": {"$in": [int(pid) for pid in scope.podcast_ids]}})
    if scope.episode_ids:
        clauses.append({"episode_id": {"$in": [int(eid) for eid in scope.episode_ids]}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def extract_used_citation_numbers(text: str) -> set[int]:
    """Parse ``[n]`` (and ``[n, m]``) citation markers from generated text."""
    used: set[int] = set()
    for group in _CITATION_MARKER_RE.findall(text):
        for part in group.split(","):
            stripped = part.strip()
            if stripped.isdigit():
                used.add(int(stripped))
    return used


def _resolve_speaker_name(ep: Episode | None, meta_speaker: str) -> str:
    if ep is not None and ep.speakers:
        if meta_speaker in ep.speakers:
            return ep.speakers[meta_speaker]
        if meta_speaker.startswith("Speaker ") and meta_speaker[8:] in ep.speakers:
            return ep.speakers[meta_speaker[8:]]
    return meta_speaker


def _make_snippet(text: str, max_len: int = 300) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def _diversify_hits(
    hits: list[ScoredPassage],
    *,
    max_per_episode: int,
    limit: int,
) -> list[ScoredPassage]:
    per_episode: dict[int, int] = {}
    kept: list[ScoredPassage] = []
    for hit in hits:
        ep_id = int(hit.passage.metadata.get("episode_id", 0))
        seen = per_episode.get(ep_id, 0)
        if seen >= max_per_episode:
            continue
        per_episode[ep_id] = seen + 1
        kept.append(hit)
        if len(kept) >= limit:
            break
    return kept


def _build_citations(selected: list[ScoredPassage]) -> list[Citation]:
    if not selected:
        return []

    ep_ids = {int(h.passage.metadata.get("episode_id", 0)) for h in selected}
    episodes_by_id: dict[int, Episode] = {}
    if ep_ids:
        with db.session_scope() as session:
            rows = session.exec(select(Episode).where(col(Episode.id).in_(ep_ids))).all()
            episodes_by_id = {ep.id: ep for ep in rows if ep.id is not None}

    citations: list[Citation] = []
    for num, hit in enumerate(selected, start=1):
        meta = hit.passage.metadata
        ep_id = int(meta.get("episode_id", 0))
        ep = episodes_by_id.get(ep_id)
        meta_speaker = str(meta.get("speaker", ""))
        speaker = _resolve_speaker_name(ep, meta_speaker)
        source_val: Literal["transcript", "summary"] = (
            "summary" if meta.get("source") == "summary" else "transcript"
        )
        citations.append(
            Citation(
                n=num,
                episode_id=ep_id,
                episode_number=ep.number if ep else 0,
                episode_title=str(meta.get("episode_title") or (ep.title if ep else "")),
                podcast_title=str(meta.get("podcast_title", "")),
                speaker=speaker,
                start=float(meta.get("start", 0.0)),
                end=float(meta.get("end", 0.0)),
                source=source_val,
                snippet=_make_snippet(hit.passage.text, 300),
            )
        )
    return citations


def _format_passages_prompt(
    citations: list[Citation],
    selected: list[ScoredPassage],
) -> str:
    if not citations:
        return "(No indexed passages matched the selected scope.)"

    blocks: list[str] = []
    for cit, hit in zip(citations, selected, strict=True):
        speaker_part = cit.speaker or "Summary"
        ts_part = f"{storage.fmt_ts(cit.start)}-{storage.fmt_ts(cit.end)}"
        header = f"[{cit.n}] {cit.podcast_title} — {cit.episode_title} | {speaker_part} ({ts_part})"
        blocks.append(f"{header}\n{hit.passage.text}")
    return "\n\n".join(blocks)


def _condense_query(prior_messages: list[Message], user_message: str) -> str:
    if not prior_messages:
        return user_message.strip()
    recent = prior_messages[-6:]
    messages: list[ChatMessage] = [
        {"role": "system", "content": CONDENSE_SYSTEM_PROMPT},
        *[{"role": m.role, "content": m.content} for m in recent],
        {"role": "user", "content": user_message},
    ]
    rewritten = get_llm().complete(messages, max_tokens=200).strip()
    return rewritten or user_message.strip()


def _conversation_title(message: str, max_len: int = 60) -> str:
    """First words of the opening question, cut at a word boundary."""
    text = " ".join(message.split()) or "New conversation"
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1].rsplit(" ", 1)[0]
    return f"{cut}…"


def answer_stream(req: ChatRequest) -> Iterator[dict[str, Any]]:
    """Run RAG retrieval and stream chat SSE event dicts."""
    title_seed = _conversation_title(req.message)

    if req.conversation_id is None:
        conv = conversations.create_conversation(title=title_seed, scope=req.scope)
        prior_messages: list[Message] = []
        effective_scope = req.scope
    else:
        existing = conversations.get_conversation(req.conversation_id)
        if existing is None:
            yield {
                "event": "error",
                "data": {"detail": f"Conversation {req.conversation_id} not found"},
            }
            return
        conv = existing
        assert conv.id is not None
        prior_messages = conversations.list_messages(conv.id)
        has_req_scope = bool(req.scope.podcast_ids or req.scope.episode_ids)
        if has_req_scope:
            effective_scope = req.scope
            conversations.patch_conversation(conv.id, ConversationPatch(scope=req.scope))
        else:
            effective_scope = Scope.model_validate(conv.scope or {})
        if not prior_messages and conv.title == "New conversation":
            conversations.patch_conversation(conv.id, ConversationPatch(title=title_seed))

    assert conv.id is not None
    user_msg = conversations.add_message(conv.id, "user", req.message)
    assert user_msg.id is not None

    store = get_vector_store()
    if store.count() == 0:
        standalone = req.message.strip()
        yield {
            "event": "meta",
            "data": {
                "conversation_id": conv.id,
                "user_message_id": user_msg.id,
                "query": standalone,
            },
        }
        yield {"event": "citations", "data": {"citations": []}}
        yield {"event": "token", "data": {"text": EMPTY_LIBRARY_MESSAGE}}
        assistant_msg = conversations.add_message(
            conv.id, "assistant", EMPTY_LIBRARY_MESSAGE, citations=[]
        )
        assert assistant_msg.id is not None
        yield {
            "event": "done",
            "data": {"assistant_message_id": assistant_msg.id, "citations": []},
        }
        return

    try:
        standalone = _condense_query(prior_messages, req.message)
        yield {
            "event": "meta",
            "data": {
                "conversation_id": conv.id,
                "user_message_id": user_msg.id,
                "query": standalone,
            },
        }

        settings = get_settings()
        query_embedding = get_embedder().embed([standalone])[0]
        where_filter = build_scope_filter(effective_scope)
        raw_hits = store.query(
            query_embedding,
            k=settings.retrieval_k * 2,
            where=where_filter,
        )
        selected = _diversify_hits(
            raw_hits,
            max_per_episode=settings.max_passages_per_episode,
            limit=settings.retrieval_k,
        )
        citations = _build_citations(selected)
        yield {
            "event": "citations",
            "data": {"citations": [c.model_dump() for c in citations]},
        }

        passages_block = _format_passages_prompt(citations, selected)
        llm_messages: list[ChatMessage] = [
            {
                "role": "system",
                "content": f"{RAG_SYSTEM_PROMPT}\n\nPassages:\n\n{passages_block}",
            },
            *[{"role": m.role, "content": m.content} for m in prior_messages[-6:]],
            {"role": "user", "content": req.message},
        ]

        pieces: list[str] = []
        for delta in get_llm().stream(llm_messages):
            if delta:
                pieces.append(delta)
                yield {"event": "token", "data": {"text": delta}}

        final_text = "".join(pieces)
        used_numbers = extract_used_citation_numbers(final_text)
        referenced = [c for c in citations if c.n in used_numbers]
        used_citations = referenced if referenced else citations
        used_dicts = [c.model_dump() for c in used_citations]

        assistant_msg = conversations.add_message(
            conv.id,
            "assistant",
            final_text,
            citations=used_dicts,
        )
        assert assistant_msg.id is not None
        yield {
            "event": "done",
            "data": {
                "assistant_message_id": assistant_msg.id,
                "citations": used_dicts,
            },
        }
    except Exception as exc:
        yield {"event": "error", "data": {"detail": str(exc)}}
