from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.actor import Actor
from app.domain.chat import SourceRef


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: str
    filename: str
    page: int
    chunk_index: int
    text: str
    score: float

    def to_source_ref(self) -> SourceRef:
        return SourceRef(
            document_id=self.document_id,
            filename=self.filename,
            page=self.page,
            chunk_index=self.chunk_index,
        )


class QueryRewriter(Protocol):
    def rewrite(self, question: str) -> str: ...


class ChunkReranker(Protocol):
    def rerank(self, query: str, chunks: Sequence[RetrievedChunk]) -> Sequence[RetrievedChunk]: ...


class ChunkRetriever(Protocol):
    def search(
        self,
        *,
        actor: Actor,
        query_vector: list[float],
        question: str,
        document_id: str | None,
        ready_ids: Sequence[str],
        top_k: int,
        score_threshold: float,
    ) -> list[RetrievedChunk]: ...
