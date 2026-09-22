from __future__ import annotations

from app.domain.actor import Actor
from app.domain.errors import NotFoundError
from app.domain.ports.documents import DocumentBytes, DocumentRepository
from app.domain.ports.ingestion import ChunkVectorStore


class DeleteDocument:
    def __init__(
        self,
        documents: DocumentRepository,
        bytes_store: DocumentBytes,
        chunk_store: ChunkVectorStore,
    ) -> None:
        self._documents = documents
        self._bytes_store = bytes_store
        self._chunk_store = chunk_store

    def execute(self, actor: Actor, document_id: str) -> str:
        document = self._documents.get(document_id)
        if document is None or document.tenant_id.value != actor.tenant_id:
            raise NotFoundError("document not found")

        self._chunk_store.delete_by_document(
            tenant_id=actor.tenant_id,
            document_id=document_id,
        )
        self._bytes_store.delete(
            tenant_id=actor.tenant_id,
            document_id=document_id,
            filename=document.filename,
        )
        self._documents.delete(document_id)
        return document_id
