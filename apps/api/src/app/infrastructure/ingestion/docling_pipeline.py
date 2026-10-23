from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any

from docling_core.types.doc.document import DoclingDocument

from app.domain.ports.ingestion import ExtractedPdf, TextChunk
from app.infrastructure.ingestion.docling_chunks import (
    PreparedDocument,
    chunk_document,
    content_blocks,
    prepare_document,
)

_converter: Any = None


class DoclingPdfPipeline:
    def __init__(self) -> None:
        self._prepared: PreparedDocument | None = None
        self._document: DoclingDocument | None = None

    def extract(self, content: bytes) -> ExtractedPdf:
        document, page_count = _convert_pdf(content)
        prepared = prepare_document(document, page_count=page_count)
        self._document = document
        self._prepared = prepared
        return ExtractedPdf(page_count=page_count, blocks=content_blocks(document))

    def chunk(self, extracted: ExtractedPdf) -> list[TextChunk]:
        del extracted
        if self._document is None or self._prepared is None:
            raise RuntimeError("extract before chunk")
        return chunk_document(
            self._document,
            self._prepared.structure,
            self._prepared.table_notes,
        )


def _convert_pdf(content: bytes) -> tuple[DoclingDocument, int]:
    from docling.datamodel.base_models import DocumentStream

    source = DocumentStream(name="document.pdf", stream=BytesIO(content))
    result = _get_converter().convert(source)
    return result.document, len(result.pages)


def _get_converter():  # noqa: ANN202
    global _converter
    if _converter is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            HeadingHierarchyOptions,
            PdfPipelineOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions(
            generate_parsed_pages=True,
            heading_hierarchy_options=HeadingHierarchyOptions(
                enabled=True,
                use_bookmarks=True,
                use_numbering=True,
                use_style=True,
            ),
        )
        artifacts = os.environ.get("DOCLING_ARTIFACTS_PATH")
        if artifacts:
            options.artifacts_path = Path(artifacts)
        _converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
    return _converter
