from __future__ import annotations

from uuid import uuid4

from app.application.documents.models import UploadDocumentCommand
from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.errors import InvalidDocument
from app.domain.ports.documents import DocumentBytes, DocumentJobQueue, DocumentRepository
from app.domain.tenancy import TenantId

_PDF_MAGIC = b"%PDF-"


class UploadDocument:
    def __init__(
        self,
        documents: DocumentRepository,
        bytes_store: DocumentBytes,
        jobs: DocumentJobQueue,
        max_size_bytes: int,
    ) -> None:
        self._documents = documents
        self._bytes_store = bytes_store
        self._jobs = jobs
        self._max_size_bytes = max_size_bytes

    def execute(self, actor: Actor, command: UploadDocumentCommand) -> Document:
        self._validate(command)
        document_id = str(uuid4())
        document = Document(
            id=document_id,
            tenant_id=TenantId(actor.tenant_id),
            filename=command.filename,
            status=DocumentStatus.PENDING,
        )
        self._bytes_store.put(
            tenant_id=actor.tenant_id,
            document_id=document_id,
            filename=command.filename,
            content=command.content,
        )
        try:
            self._documents.save(document)
            self._jobs.enqueue(
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                document_id=document_id,
            )
        except Exception:
            self._bytes_store.delete(
                tenant_id=actor.tenant_id,
                document_id=document_id,
                filename=command.filename,
            )
            raise
        return document

    def _validate(self, command: UploadDocumentCommand) -> None:
        if not command.content.startswith(_PDF_MAGIC):
            raise InvalidDocument("file must be a PDF")
        if len(command.content) > self._max_size_bytes:
            raise InvalidDocument("file exceeds size limit")
        filename = command.filename
        if not filename or "/" in filename or "\\" in filename or "\x00" in filename:
            raise InvalidDocument("invalid filename")
