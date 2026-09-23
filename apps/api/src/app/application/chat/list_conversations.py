from __future__ import annotations

from app.domain.actor import Actor
from app.domain.chat import Conversation
from app.domain.ports.conversations import ConversationRepository


class ListConversations:
    def __init__(self, conversations: ConversationRepository) -> None:
        self._conversations = conversations

    def execute(self, actor: Actor) -> list[Conversation]:
        return self._conversations.list_for_actor(actor)
