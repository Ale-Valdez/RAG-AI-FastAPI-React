from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

ElementType = Literal["text", "list", "table"]
DocumentStructure = Literal["headed", "flat"]
BlockKind = Literal[
    "title",
    "section_header",
    "text",
    "list_item",
    "table",
    "code",
    "formula",
]


@dataclass(frozen=True)
class ContentBlock:
    kind: BlockKind
    level: int | None
    text: str
    page: int


@dataclass(frozen=True)
class ExtractedPdf:
    page_count: int
    blocks: list[ContentBlock]


@dataclass(frozen=True)
class TextChunk:
    page: int
    chunk_index: int
    text: str
    section_path: tuple[str, ...] = ()
    heading: str | None = None
    page_end: int | None = None
    element_type: ElementType = "text"
    structure: DocumentStructure = "flat"

    @property
    def resolved_page_end(self) -> int:
        if self.page_end is None:
            return self.page
        return self.page_end


class PdfTextExtractor(Protocol):
    def extract(self, content: bytes) -> ExtractedPdf: ...


class TextChunker(Protocol):
    def chunk(self, extracted: ExtractedPdf) -> list[TextChunk]: ...


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
