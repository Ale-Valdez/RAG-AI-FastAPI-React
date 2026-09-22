from __future__ import annotations

from app.domain.actor import Actor
from app.domain.documents import Document
from app.domain.errors import NotFoundError
from app.domain.ports.documents import DocumentJobQueue, DocumentRepository


class ReingestDocument:
    def __init__(
        self,
        documents: DocumentRepository,
        jobs: DocumentJobQueue,
    ) -> None:
        self._documents = documents
        self._jobs = jobs

    def execute(self, actor: Actor, document_id: str) -> Document:
        document = self._documents.get(document_id)
        if document is None or document.tenant_id.value != actor.tenant_id:
            raise NotFoundError("document not found")

        document.mark_pending()
        self._documents.save(document)
        self._jobs.enqueue(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            document_id=document_id,
        )
        return document
