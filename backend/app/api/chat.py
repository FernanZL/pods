"""Streaming RAG chat endpoint (Server-Sent Events)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from app.providers import get_embedder, get_llm
from app.schemas import ChatRequest
from app.services import conversations, rag
from app.services.vectorstore import get_vector_store

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat_endpoint(req: ChatRequest) -> EventSourceResponse:
    """Stream a RAG chat answer as Server-Sent Events."""
    if (
        req.conversation_id is not None
        and conversations.get_conversation(req.conversation_id) is None
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")

    if get_vector_store().count() > 0:
        get_embedder()
        get_llm()

    async def _event_publisher() -> AsyncIterator[dict[str, str]]:
        async for event in iterate_in_threadpool(rag.answer_stream(req)):
            yield {
                "event": str(event["event"]),
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(_event_publisher())
