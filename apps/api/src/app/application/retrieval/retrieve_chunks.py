from __future__ import annotations

from app.domain.actor import Actor
from app.domain.documents import DocumentStatus
from app.domain.errors import NotFoundError
from app.domain.ports.documents import DocumentRepository
from app.domain.ports.ingestion import EmbeddingGenerator
from app.domain.ports.retrieval import ChunkRetriever, RetrievedChunk
from app.domain.tenancy import TenantId


class RetrieveChunks:
    def __init__(
        self,
        documents: DocumentRepository,
        embeddings: EmbeddingGenerator,
        retriever: ChunkRetriever,
        *,
        top_k: int,
        score_threshold: float,
    ) -> None:
        self._documents = documents
        self._embeddings = embeddings
        self._retriever = retriever
        self._top_k = top_k
        self._score_threshold = score_threshold

    def execute(
        self,
        actor: Actor,
        question: str,
        document_id: str | None = None,
    ) -> list[RetrievedChunk]:
        ready_ids = self._ready_ids(actor, document_id)
        if not ready_ids:
            return []

        query_vector = self._embeddings.embed([question])[0]
        return self._retriever.search(
            actor=actor,
            query_vector=query_vector,
            document_id=document_id,
            ready_ids=ready_ids,
            top_k=self._top_k,
            score_threshold=self._score_threshold,
        )

    def _ready_ids(self, actor: Actor, document_id: str | None) -> list[str]:
        if document_id is not None:
            document = self._documents.get(document_id)
            if (
                document is None
                or document.tenant_id.value != actor.tenant_id
                or document.status is not DocumentStatus.READY
            ):
                raise NotFoundError("document not found")
            return [document.id]

        return [
            document.id
            for document in self._documents.list_for_tenant(TenantId(actor.tenant_id))
            if document.status is DocumentStatus.READY
        ]
