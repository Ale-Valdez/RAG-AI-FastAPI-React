from __future__ import annotations

from app.domain.actor import Actor
from app.domain.chat import Conversation
from app.domain.errors import NotFoundError
from app.domain.ports.conversations import ConversationRepository


class GetConversation:
    def __init__(self, conversations: ConversationRepository) -> None:
        self._conversations = conversations

    def execute(self, actor: Actor, conversation_id: str) -> Conversation:
        conversation = self._conversations.get_for_actor(actor, conversation_id)
        if conversation is None:
            raise NotFoundError("conversation not found")
        return conversation
