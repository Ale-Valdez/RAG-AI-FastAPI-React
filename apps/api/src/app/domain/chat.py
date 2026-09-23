from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.domain.identity import UserId
from app.domain.tenancy import TenantId


@dataclass(frozen=True)
class SourceRef:
    document_id: str
    filename: str
    page: int
    chunk_index: int


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    sources: tuple[SourceRef, ...] = ()


@dataclass
class Conversation:
    id: str
    tenant_id: TenantId
    user_id: UserId
    created_at: datetime
    messages: list[Message] = field(default_factory=list)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
