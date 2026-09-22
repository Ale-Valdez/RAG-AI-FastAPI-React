from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PageText:
    page: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    page: int
    chunk_index: int
    text: str


class PdfTextExtractor(Protocol):
    def extract_pages(self, content: bytes) -> list[PageText]: ...


class TextChunker(Protocol):
    def chunk_pages(self, pages: list[PageText]) -> list[TextChunk]: ...


class EmbeddingGenerator(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChunkVectorStore(Protocol):
    def delete_by_document(self, *, tenant_id: str, document_id: str) -> None: ...

    def upsert_chunks(
        self,
        *,
        tenant_id: str,
        document_id: str,
        filename: str,
        chunks: list[TextChunk],
        vectors: list[list[float]],
    ) -> None: ...
