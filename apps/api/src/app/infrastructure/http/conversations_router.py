from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.domain.actor import Actor
from app.domain.chat import Conversation, Message, SourceRef
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.http.dependencies.auth import build_require_actor
from app.infrastructure.http.responses.api_response import success_body


class AskBody(BaseModel):
    question: str
    document_id: str | None = None


class AskQuestionUseCase(Protocol):
    def execute(
        self,
        actor: Actor,
        question: str,
        document_id: str | None = None,
        conversation_id: str | None = None,
    ) -> Conversation: ...


class GetConversationUseCase(Protocol):
    def execute(self, actor: Actor, conversation_id: str) -> Conversation: ...


class ListConversationsUseCase(Protocol):
    def execute(self, actor: Actor) -> list[Conversation]: ...


def _source_payload(source: SourceRef) -> dict[str, object]:
    return {
        "document_id": source.document_id,
        "filename": source.filename,
        "page": source.page,
        "chunk_index": source.chunk_index,
    }


def _message_payload(message: Message) -> dict[str, object]:
    return {
        "role": message.role,
        "content": message.content,
        "sources": [_source_payload(source) for source in message.sources],
    }


def _conversation_payload(conversation: Conversation) -> dict[str, object]:
    return {
        "id": conversation.id,
        "messages": [_message_payload(message) for message in conversation.messages],
    }


def build_conversations_router(
    *,
    ask_question: AskQuestionUseCase,
    get_conversation: GetConversationUseCase,
    list_conversations: ListConversationsUseCase,
    jwt_service: JwtService,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    require_actor = build_require_actor(jwt_service)

    @router.post("/conversations")
    def conversations_create(
        body: AskBody,
        actor: Actor = Depends(require_actor),
    ) -> JSONResponse:
        conversation = ask_question.execute(actor, body.question, body.document_id, None)
        return JSONResponse(success_body(_conversation_payload(conversation)), status_code=201)

    @router.post("/conversations/{conversation_id}/messages")
    def conversations_append(
        conversation_id: str,
        body: AskBody,
        actor: Actor = Depends(require_actor),
    ) -> JSONResponse:
        conversation = ask_question.execute(
            actor,
            body.question,
            body.document_id,
            conversation_id,
        )
        return JSONResponse(success_body(_conversation_payload(conversation)), status_code=200)

    @router.get("/conversations/{conversation_id}")
    def conversations_get(
        conversation_id: str,
        actor: Actor = Depends(require_actor),
    ) -> JSONResponse:
        conversation = get_conversation.execute(actor, conversation_id)
        return JSONResponse(success_body(_conversation_payload(conversation)), status_code=200)

    @router.get("/conversations")
    def conversations_list(actor: Actor = Depends(require_actor)) -> JSONResponse:
        conversations = list_conversations.execute(actor)
        return JSONResponse(
            success_body(
                {
                    "conversations": [
                        {"id": item.id, "created_at": item.created_at.isoformat()}
                        for item in conversations
                    ]
                }
            ),
            status_code=200,
        )

    return router
