from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from app.domain.ports.ingestion import PageText


class PypdfTextExtractor:
    def extract_pages(self, content: bytes) -> list[PageText]:
        reader = PdfReader(BytesIO(content))
        pages: list[PageText] = []
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append(PageText(page=index, text=text))
        return pages
