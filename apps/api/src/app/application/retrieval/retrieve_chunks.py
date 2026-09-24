from __future__ import annotations

from collections.abc import Sequence

from app.domain.actor import Actor
from app.domain.documents import DocumentStatus
from app.domain.errors import NotFoundError
from app.domain.ports.documents import DocumentRepository
from app.domain.ports.ingestion import EmbeddingGenerator
from app.domain.ports.retrieval import (
    ChunkReranker,
    ChunkRetriever,
    QueryRewriter,
    RetrievedChunk,
)
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
        rewriter: QueryRewriter | None = None,
        reranker: ChunkReranker | None = None,
    ) -> None:
        self._documents = documents
        self._embeddings = embeddings
        self._retriever = retriever
        self._top_k = top_k
        self._score_threshold = score_threshold
        self._rewriter = rewriter
        self._reranker = reranker

    def execute(
        self,
        actor: Actor,
        question: str,
        document_id: str | None = None,
    ) -> list[RetrievedChunk]:
        ready_ids = self._ready_ids(actor, document_id)
        if not ready_ids:
            return []

        query = self._retrieval_query(question)
        query_vector = self._embeddings.embed([query])[0]
        hits = self._retriever.search(
            actor=actor,
            query_vector=query_vector,
            question=query,
            document_id=document_id,
            ready_ids=ready_ids,
            top_k=self._top_k,
            score_threshold=self._score_threshold,
        )
        ranked = self._rerank(query, hits)
        return [hit for hit in ranked if hit.score >= self._score_threshold]

    def _retrieval_query(self, question: str) -> str:
        if self._rewriter is None:
            return question
        try:
            rewritten = self._rewriter.rewrite(question)
        except Exception:
            return question
        if not isinstance(rewritten, str) or not rewritten.strip():
            return question
        return rewritten.strip()

    def _rerank(self, query: str, hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if self._reranker is None or not hits:
            return hits
        try:
            reranked = self._reranker.rerank(query, hits)
        except Exception:
            return hits
        if not _same_chunks(hits, reranked):
            return hits
        return list(reranked)

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


def _same_chunks(left: Sequence[RetrievedChunk], right: object) -> bool:
    if isinstance(right, (str, bytes)) or not isinstance(right, Sequence):
        return False
    if len(left) != len(right):
        return False
    right_keys: list[tuple[str, int]] = []
    for item in right:
        if not isinstance(item, RetrievedChunk):
            return False
        right_keys.append((item.document_id, item.chunk_index))
    left_keys = [(item.document_id, item.chunk_index) for item in left]
    return sorted(left_keys) == sorted(right_keys)
