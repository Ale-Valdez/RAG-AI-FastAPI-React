from __future__ import annotations

from app.domain.ports.ingestion import PageText, TextChunk

_MAX_CHUNK_CHARS = 1000


class PageAwareChunker:
    def chunk_pages(self, pages: list[PageText]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        chunk_index = 0
        for page in pages:
            for piece in _split_page(page.text):
                chunks.append(
                    TextChunk(page=page.page, chunk_index=chunk_index, text=piece)
                )
                chunk_index += 1
        return chunks


def _split_page(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    pieces: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= _MAX_CHUNK_CHARS:
            pieces.append(remaining)
            break
        window = remaining[:_MAX_CHUNK_CHARS]
        split_at = window.rfind(" ")
        if split_at <= 0:
            split_at = _MAX_CHUNK_CHARS
        pieces.append(remaining[:split_at])
        remaining = remaining[split_at:]
        if remaining.startswith(" "):
            remaining = remaining[1:]
    return pieces
