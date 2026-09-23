from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.application.retrieval.retrieve_chunks import RetrieveChunks
from app.domain.actor import Actor
from app.domain.chat import Conversation, Message, SourceRef
from app.domain.errors import DomainError, NotFoundError
from app.domain.identity import UserId
from app.domain.ports.conversations import ConversationRepository
from app.domain.ports.generation import AnswerGenerator
from app.domain.tenancy import TenantId

_REFUSAL = "I don't know based on the ready documents."


class AskQuestion:
    def __init__(
        self,
        conversations: ConversationRepository,
        retrieve: RetrieveChunks,
        generator: AnswerGenerator,
    ) -> None:
        self._conversations = conversations
        self._retrieve = retrieve
        self._generator = generator

    def execute(
        self,
        actor: Actor,
        question: str,
        document_id: str | None = None,
        conversation_id: str | None = None,
    ) -> Conversation:
        if not question.strip():
            raise DomainError("question is required")

        if conversation_id is None:
            conversation = Conversation(
                id=str(uuid4()),
                tenant_id=TenantId(actor.tenant_id),
                user_id=UserId(actor.user_id),
                created_at=datetime.now(UTC),
            )
        else:
            loaded = self._conversations.get_for_actor(actor, conversation_id)
            if loaded is None:
                raise NotFoundError("conversation not found")
            conversation = loaded

        chunks = self._retrieve.execute(actor, question, document_id)
        if chunks:
            answer = self._generator.generate(question, [chunk.text for chunk in chunks])
            sources: tuple[SourceRef, ...] = tuple(chunk.to_source_ref() for chunk in chunks)
        else:
            answer = _REFUSAL
            sources = ()

        conversation.add_message(Message(role="user", content=question))
        conversation.add_message(Message(role="assistant", content=answer, sources=sources))
        self._conversations.save(conversation)
        return conversation
