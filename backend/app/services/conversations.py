"""Conversation and message persistence helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

from sqlalchemy import func
from sqlmodel import Session, col, select

from app import db
from app.models import Conversation, Message, utcnow
from app.schemas import (
    Citation,
    ConversationDetail,
    ConversationOut,
    ConversationPatch,
    MessageOut,
    Scope,
)


@contextmanager
def _session_ctx(session: Session | None = None) -> Iterator[Session]:
    if session is not None:
        yield session
    else:
        with db.session_scope() as owned:
            yield owned


def create_conversation(
    title: str = "New conversation",
    scope: Scope | None = None,
    *,
    session: Session | None = None,
) -> Conversation:
    """Create and persist a new conversation."""
    scope_dict = scope.model_dump() if scope is not None else Scope().model_dump()
    with _session_ctx(session) as s:
        conv = Conversation(title=title, scope=scope_dict)
        s.add(conv)
        s.commit()
        s.refresh(conv)
        return conv


def get_conversation(
    conversation_id: int,
    *,
    session: Session | None = None,
) -> Conversation | None:
    """Fetch a conversation by primary key, or None if missing."""
    with _session_ctx(session) as s:
        return s.get(Conversation, conversation_id)


def list_messages(
    conversation_id: int,
    *,
    session: Session | None = None,
) -> list[Message]:
    """Return all messages in a conversation ordered chronologically."""
    with _session_ctx(session) as s:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(col(Message.created_at).asc(), col(Message.id).asc())
        )
        return [m for m in s.exec(stmt).all()]


def message_to_out(msg: Message) -> MessageOut:
    """Convert a ``Message`` row into a ``MessageOut`` schema."""
    assert msg.id is not None
    role: Literal["user", "assistant"] = "assistant" if msg.role == "assistant" else "user"
    citations = [Citation.model_validate(c) for c in (msg.citations or [])]
    return MessageOut(
        id=msg.id,
        role=role,
        content=msg.content,
        citations=citations,
        created_at=msg.created_at,
    )


def to_out(
    conv: Conversation,
    message_count: int | None = None,
    *,
    session: Session | None = None,
) -> ConversationOut:
    """Convert a ``Conversation`` row into a ``ConversationOut`` schema."""
    assert conv.id is not None
    if message_count is None:
        with _session_ctx(session) as s:
            count_stmt = (
                select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
            )
            message_count = int(s.exec(count_stmt).one())
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        scope=Scope.model_validate(conv.scope or {}),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=message_count,
    )


def to_detail(
    conv: Conversation,
    messages: list[Message] | None = None,
    *,
    session: Session | None = None,
) -> ConversationDetail:
    """Convert a ``Conversation`` row and its messages into ``ConversationDetail``."""
    assert conv.id is not None
    msgs = messages if messages is not None else list_messages(conv.id, session=session)
    msg_outs = [message_to_out(m) for m in msgs]
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        scope=Scope.model_validate(conv.scope or {}),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(msg_outs),
        messages=msg_outs,
    )


def list_conversations(*, session: Session | None = None) -> list[ConversationOut]:
    """Return all conversations ordered from most recently updated to oldest."""
    with _session_ctx(session) as s:
        convs = [
            c
            for c in s.exec(
                select(Conversation).order_by(
                    col(Conversation.updated_at).desc(),
                    col(Conversation.id).desc(),
                )
            ).all()
        ]
        if not convs:
            return []

        counts_stmt = select(Message.conversation_id, func.count(col(Message.id))).group_by(
            col(Message.conversation_id)
        )
        counts: dict[int, int] = {int(cid): int(cnt) for cid, cnt in s.exec(counts_stmt).all()}
        return [to_out(c, message_count=counts.get(c.id or 0, 0), session=s) for c in convs]


def patch_conversation(
    conversation_id: int,
    patch_data: ConversationPatch,
    *,
    session: Session | None = None,
) -> Conversation | None:
    """Update title and/or scope on an existing conversation."""
    with _session_ctx(session) as s:
        conv = s.get(Conversation, conversation_id)
        if conv is None:
            return None
        if patch_data.title is not None:
            conv.title = patch_data.title
        if patch_data.scope is not None:
            conv.scope = patch_data.scope.model_dump()
        conv.updated_at = utcnow()
        s.add(conv)
        s.commit()
        s.refresh(conv)
        return conv


def delete_conversation(
    conversation_id: int,
    *,
    session: Session | None = None,
) -> bool:
    """Delete a conversation and all its messages. Return False if not found."""
    with _session_ctx(session) as s:
        conv = s.get(Conversation, conversation_id)
        if conv is None:
            return False
        msgs = s.exec(select(Message).where(Message.conversation_id == conversation_id)).all()
        for msg in msgs:
            s.delete(msg)
        s.flush()
        s.delete(conv)
        s.commit()
        return True


def add_message(
    conversation_id: int,
    role: Literal["user", "assistant"],
    content: str,
    citations: list[Citation] | list[dict[str, Any]] | None = None,
    *,
    session: Session | None = None,
) -> Message:
    """Append a message to a conversation and update ``Conversation.updated_at``."""
    serialized_citations: list[dict[str, Any]] = []
    if citations:
        for item in citations:
            if isinstance(item, Citation):
                serialized_citations.append(item.model_dump())
            else:
                serialized_citations.append(dict(item))

    with _session_ctx(session) as s:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=serialized_citations,
        )
        s.add(msg)
        conv = s.get(Conversation, conversation_id)
        if conv is not None:
            conv.updated_at = utcnow()
            s.add(conv)
        s.commit()
        s.refresh(msg)
        return msg


# Short CRUD aliases matching task overview
create = create_conversation
get = get_conversation
list = list_conversations
patch = patch_conversation
delete = delete_conversation
