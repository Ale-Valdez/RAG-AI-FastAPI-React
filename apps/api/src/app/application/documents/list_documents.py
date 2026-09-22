from __future__ import annotations

from app.domain.actor import Actor
from app.domain.documents import Document
from app.domain.ports.documents import DocumentRepository
from app.domain.tenancy import TenantId


class ListDocuments:
    def __init__(self, documents: DocumentRepository) -> None:
        self._documents = documents

    def execute(self, actor: Actor) -> list[Document]:
        return self._documents.list_for_tenant(TenantId(actor.tenant_id))
