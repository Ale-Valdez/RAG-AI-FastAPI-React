from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.ports.documents import DocumentBytes, DocumentRepository
from app.domain.ports.ingestion import (
    ChunkVectorStore,
    EmbeddingGenerator,
    PdfTextExtractor,
    TextChunker,
)
from app.domain.tenancy import TenantId, assert_same_tenant


class ProcessOutcome(str, Enum):
    READY = "ready"
    FAILED = "failed"
    DEFERRED = "deferred"
    SKIPPED = "skipped"


class ProcessDocument:
    def __init__(
        self,
        documents: DocumentRepository,
        bytes_store: DocumentBytes,
        extractor: PdfTextExtractor,
        chunker: TextChunker,
        embeddings: EmbeddingGenerator,
        chunk_store: ChunkVectorStore,
        *,
        max_pages: int,
        max_concurrent: int,
        commit: Callable[[], None] | None = None,
    ) -> None:
        self._documents = documents
        self._bytes_store = bytes_store
        self._extractor = extractor
        self._chunker = chunker
        self._embeddings = embeddings
        self._chunk_store = chunk_store
        self._max_pages = max_pages
        self._max_concurrent = max_concurrent
        self._commit = commit or (lambda: None)

    def execute(self, actor: Actor, document_id: str) -> ProcessOutcome:
        document = self._documents.get(document_id)
        if document is None:
            return ProcessOutcome.SKIPPED

        assert_same_tenant(document.tenant_id, TenantId(actor.tenant_id))

        if document.status is not DocumentStatus.PENDING:
            return ProcessOutcome.SKIPPED

        if self._documents.count_processing(document.tenant_id) >= self._max_concurrent:
            return ProcessOutcome.DEFERRED

        document.mark_processing()
        self._documents.save(document)
        self._commit()

        return self._ingest(actor, document)

    def _ingest(self, actor: Actor, document: Document) -> ProcessOutcome:
        try:
            content = self._bytes_store.get(
                tenant_id=actor.tenant_id,
                document_id=document.id,
                filename=document.filename,
            )
            pages = self._extractor.extract_pages(content)
        except Exception:
            return self._fail(document)

        if len(pages) > self._max_pages:
            return self._fail(document)

        chunks = self._chunker.chunk_pages(pages)
        if not chunks:
            return self._fail(document)

        try:
            vectors = self._embeddings.embed([chunk.text for chunk in chunks])
            if self._documents.get(document.id) is None:
                return ProcessOutcome.SKIPPED
            self._chunk_store.delete_by_document(
                tenant_id=actor.tenant_id,
                document_id=document.id,
            )
            self._chunk_store.upsert_chunks(
                tenant_id=actor.tenant_id,
                document_id=document.id,
                filename=document.filename,
                chunks=chunks,
                vectors=vectors,
            )
        except Exception:
            return self._fail(document)

        return self._ready(document)

    def _fail(self, document: Document) -> ProcessOutcome:
        try:
            self._chunk_store.delete_by_document(
                tenant_id=document.tenant_id.value,
                document_id=document.id,
            )
        except Exception:
            pass
        if self._documents.get(document.id) is None:
            return ProcessOutcome.SKIPPED
        if document.status is DocumentStatus.PROCESSING:
            document.mark_failed()
            self._documents.save(document)
        return ProcessOutcome.FAILED

    def _ready(self, document: Document) -> ProcessOutcome:
        if self._documents.get(document.id) is None:
            self._chunk_store.delete_by_document(
                tenant_id=document.tenant_id.value,
                document_id=document.id,
            )
            return ProcessOutcome.SKIPPED
        document.mark_ready()
        self._documents.save(document)
        return ProcessOutcome.READY
