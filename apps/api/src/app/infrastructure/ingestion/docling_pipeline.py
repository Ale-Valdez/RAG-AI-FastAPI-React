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

_converters: dict[bool, Any] = {}


class DoclingPdfPipeline:
    def __init__(self) -> None:
        self._prepared: PreparedDocument | None = None
        self._document: DoclingDocument | None = None

    def count_pages(self, content: bytes) -> int:
        return _pdf_page_count(content)

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

    page_count = _pdf_page_count(content)
    do_ocr = not _pdf_has_text_layer(content)
    source = DocumentStream(name="document.pdf", stream=BytesIO(content))
    result = _get_converter(do_ocr=do_ocr).convert(source)
    document = result.document
    # The conversion result keeps rendered page bitmaps. The document does not need them.
    result.pages = []
    del result
    return document, page_count


def _pdf_page_count(content: bytes) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(content)
    try:
        return len(pdf)
    finally:
        pdf.close()


def _pdf_has_text_layer(content: bytes) -> bool:
    """Digital PDFs skip OCR. OCR renders every page at 3x and is what exhausts RAM."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(content)
    try:
        sample = min(3, len(pdf))
        for index in range(sample):
            page = pdf[index]
            textpage = page.get_textpage()
            try:
                if len(textpage.get_text_bounded().strip()) >= 20:
                    return True
            finally:
                textpage.close()
                page.close()
        return False
    finally:
        pdf.close()


def _get_converter(*, do_ocr: bool):  # noqa: ANN202
    cached = _converters.get(do_ocr)
    if cached is not None:
        return cached

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorOptions,
        HeadingHierarchyOptions,
        OcrAutoOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=do_ocr,
        force_backend_text=not do_ocr,
        generate_parsed_pages=False,
        images_scale=1.0,
        layout_batch_size=1,
        ocr_batch_size=1,
        table_batch_size=1,
        accelerator_options=AcceleratorOptions(num_threads=2, device="cpu"),
        ocr_options=OcrAutoOptions(scale=1.0),
        table_structure_options=TableStructureOptions(
            do_cell_matching=True,
            mode=TableFormerMode.FAST,
        ),
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
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    _converters[do_ocr] = converter
    return converter
