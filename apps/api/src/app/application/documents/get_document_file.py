from __future__ import annotations

from dataclasses import dataclass

from app.domain.actor import Actor
from app.domain.errors import NotFoundError
from app.domain.ports.documents import DocumentBytes, DocumentRepository


@dataclass(frozen=True)
class DocumentFile:
    filename: str
    content: bytes


class GetDocumentFile:
    def __init__(self, documents: DocumentRepository, bytes_store: DocumentBytes) -> None:
        self._documents = documents
        self._bytes_store = bytes_store

    def execute(self, actor: Actor, document_id: str) -> DocumentFile:
        document = self._documents.get(document_id)
        if document is None or document.tenant_id.value != actor.tenant_id:
            raise NotFoundError("document not found")

        try:
            content = self._bytes_store.get(
                tenant_id=actor.tenant_id,
                document_id=document_id,
                filename=document.filename,
            )
        except KeyError as exc:
            raise NotFoundError("document not found") from exc
        return DocumentFile(filename=document.filename, content=content)
