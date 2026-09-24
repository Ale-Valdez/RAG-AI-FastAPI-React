from __future__ import annotations

import re

from app.domain.ports.retrieval import RetrievedChunk

_STOP_WORDS = frozenset(
    {"what", "when", "where", "does", "this", "that", "with", "from", "have", "which"}
)
_WORD = re.compile(r"[^\W_]+")
_RRF_K = 60


def query_words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def distinctive_words(query: str) -> list[str]:
    return [word for word in query_words(query) if len(word) >= 4 and word not in _STOP_WORDS]


def lexical_score(query: str, passage: str) -> float:
    required = distinctive_words(query)
    if not required:
        return 0.0
    present = set(query_words(passage))
    if all(word in present for word in required):
        return 1.0
    return 0.0


def fuse_hits(
    dense: list[RetrievedChunk],
    text: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    weights: dict[tuple[str, int], float] = {}
    best: dict[tuple[str, int], RetrievedChunk] = {}

    def add(hits: list[RetrievedChunk]) -> None:
        for rank, hit in enumerate(hits, start=1):
            key = (hit.document_id, hit.chunk_index)
            weights[key] = weights.get(key, 0.0) + (1.0 / (_RRF_K + rank))
            current = best.get(key)
            if current is None or hit.score > current.score:
                best[key] = hit

    add(dense)
    add(text)
    ordered = sorted(
        best.values(),
        key=lambda hit: (
            -weights[(hit.document_id, hit.chunk_index)],
            hit.document_id,
            hit.chunk_index,
        ),
    )
    return ordered[:top_k]
