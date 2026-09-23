from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.actor import Actor
from app.domain.chat import Conversation, Message, SourceRef
from app.domain.identity import UserId
from app.domain.tenancy import TenantId
from app.infrastructure.persistence.models import ConversationRow, MessageRow


class SqlAlchemyConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, conversation: Conversation) -> None:
        existing = self._session.get(ConversationRow, conversation.id)
        if existing is None:
            self._session.add(
                ConversationRow(
                    id=conversation.id,
                    tenant_id=conversation.tenant_id.value,
                    user_id=conversation.user_id.value,
                    created_at=conversation.created_at,
                )
            )
        else:
            existing.tenant_id = conversation.tenant_id.value
            existing.user_id = conversation.user_id.value
        self._session.flush()
        self._session.execute(
            delete(MessageRow).where(MessageRow.conversation_id == conversation.id)
        )
        for position, message in enumerate(conversation.messages):
            self._session.add(
                MessageRow(
                    id=str(uuid4()),
                    conversation_id=conversation.id,
                    tenant_id=conversation.tenant_id.value,
                    position=position,
                    role=message.role,
                    content=message.content,
                    sources=_sources_to_json(message.sources),
                )
            )

    def get_for_actor(self, actor: Actor, conversation_id: str) -> Conversation | None:
        row = self._session.scalar(
            select(ConversationRow).where(
                ConversationRow.id == conversation_id,
                ConversationRow.tenant_id == actor.tenant_id,
                ConversationRow.user_id == actor.user_id,
            )
        )
        if row is None:
            return None
        messages = self._session.scalars(
            select(MessageRow)
            .where(
                MessageRow.conversation_id == row.id,
                MessageRow.tenant_id == actor.tenant_id,
            )
            .order_by(MessageRow.position.asc())
        ).all()
        return _to_domain(row, messages)

    def list_for_actor(self, actor: Actor) -> list[Conversation]:
        rows = self._session.scalars(
            select(ConversationRow)
            .where(
                ConversationRow.tenant_id == actor.tenant_id,
                ConversationRow.user_id == actor.user_id,
            )
            .order_by(ConversationRow.created_at.desc(), ConversationRow.id.desc())
        ).all()
        return [_to_domain(row, []) for row in rows]


def _sources_to_json(sources: tuple[SourceRef, ...]) -> list[dict[str, object]]:
    return [
        {
            "document_id": source.document_id,
            "filename": source.filename,
            "page": source.page,
            "chunk_index": source.chunk_index,
        }
        for source in sources
    ]


def _sources_from_json(raw: object) -> tuple[SourceRef, ...]:
    if not isinstance(raw, list):
        return ()
    sources: list[SourceRef] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sources.append(
            SourceRef(
                document_id=str(item["document_id"]),
                filename=str(item["filename"]),
                page=int(item["page"]),
                chunk_index=int(item["chunk_index"]),
            )
        )
    return tuple(sources)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_domain(row: ConversationRow, messages: list[MessageRow]) -> Conversation:
    return Conversation(
        id=row.id,
        tenant_id=TenantId(row.tenant_id),
        user_id=UserId(row.user_id),
        created_at=_as_utc(row.created_at),
        messages=[
            Message(
                role=message.role,
                content=message.content,
                sources=_sources_from_json(message.sources),
            )
            for message in messages
        ],
    )
