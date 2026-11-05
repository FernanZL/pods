"""Conversation CRUD endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app.db import get_session
from app.schemas import ConversationDetail, ConversationOut, ConversationPatch
from app.services import conversations

router = APIRouter(tags=["conversations"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations_endpoint(session: SessionDep) -> list[ConversationOut]:
    """List conversations ordered from most recently updated to oldest."""
    return conversations.list_conversations(session=session)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation_endpoint(
    conversation_id: int,
    session: SessionDep,
) -> ConversationDetail:
    """Return a single conversation and its chronological messages."""
    conv = conversations.get_conversation(conversation_id, session=session)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations.to_detail(conv, session=session)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def patch_conversation_endpoint(
    conversation_id: int,
    patch_body: ConversationPatch,
    session: SessionDep,
) -> ConversationOut:
    """Update a conversation's title and/or retrieval scope."""
    conv = conversations.patch_conversation(conversation_id, patch_body, session=session)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations.to_out(conv, session=session)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation_endpoint(
    conversation_id: int,
    session: SessionDep,
) -> Response:
    """Delete a conversation and all of its messages."""
    deleted = conversations.delete_conversation(conversation_id, session=session)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return Response(status_code=204)
