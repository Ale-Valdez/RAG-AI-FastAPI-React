from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.actor import Actor


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: str
    filename: str
    page: int
    chunk_index: int
    text: str
    score: float


class ChunkRetriever(Protocol):
    def search(
        self,
        *,
        actor: Actor,
        query_vector: list[float],
        document_id: str | None,
        ready_ids: Sequence[str],
        top_k: int,
        score_threshold: float,
    ) -> list[RetrievedChunk]: ...
