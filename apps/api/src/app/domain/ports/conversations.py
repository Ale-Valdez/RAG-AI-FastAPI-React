from __future__ import annotations

from typing import Protocol

from app.domain.actor import Actor
from app.domain.chat import Conversation


class ConversationRepository(Protocol):
    def save(self, conversation: Conversation) -> None: ...

    def get_for_actor(self, actor: Actor, conversation_id: str) -> Conversation | None: ...

    def list_for_actor(self, actor: Actor) -> list[Conversation]: ...
