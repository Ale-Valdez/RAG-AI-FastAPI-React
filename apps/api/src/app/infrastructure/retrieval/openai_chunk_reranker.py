from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from openai import OpenAI

from app.domain.ports.retrieval import RetrievedChunk

_INDEX = re.compile(r"\d+")


class OpenAIChunkReranker:
    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self._client = OpenAI(api_key=api_key) if client is None else client
        self._model = model

    def rerank(self, query: str, chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        labeled = "\n".join(f"[{index}] {chunk.text}" for index, chunk in enumerate(chunks))
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Rank the passages for the query. "
                        "Each passage is labeled with a bracket index that starts at 0. "
                        "Copy the bracket indexes. "
                        "Return only those indexes in best-first order.\n\n"
                        f"Query: {query}\n\n"
                        f"Passages:\n{labeled}"
                    ),
                }
            ],
        )
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("empty rerank")
        order = _rank_order(content, len(chunks))
        return [chunks[index] for index in order]


def _rank_order(content: str, count: int) -> list[int]:
    found = [int(token) for token in _INDEX.findall(content)]
    if sorted(found) != list(range(count)):
        raise ValueError("rerank order is not a 0-based permutation")
    return found
