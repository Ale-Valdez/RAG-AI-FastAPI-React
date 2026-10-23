from __future__ import annotations

import pytest
import tiktoken
from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
from docling_core.types.doc.common.reference import ProvenanceItem, RefItem
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.table.table_data import TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel

from app.infrastructure.ingestion.docling_chunks import chunk_document, prepare_document


def _prov(page: int, text: str = "x") -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page,
        bbox=BoundingBox(l=0, t=0, r=10, b=10, coord_origin=CoordOrigin.TOPLEFT),
        charspan=(0, len(text)),
    )


def _document(name: str, pages: int = 1) -> DoclingDocument:
    document = DoclingDocument(name=name)
    for page in range(1, pages + 1):
        document.add_page(page, size=Size(width=100, height=100))
    return document


def _labels(document: DoclingDocument) -> set[str]:
    from docling_core.types.doc.common.content_layer import ContentLayer

    found: set[str] = set()
    for item, _level in document.iterate_items(
        with_groups=True,
        traverse_pictures=True,
        included_content_layers=set(ContentLayer),
    ):
        label = getattr(item, "label", None)
        if label is not None:
            found.add(label.value)
    return found


def _chunks(document: DoclingDocument):
    prepared = prepare_document(document)
    return chunk_document(document, prepared.structure, prepared.table_notes), prepared


def test_headed_paragraphs_share_a_path_and_a_new_subtitle_does_not() -> None:
    document = _document("policy.pdf")
    document.add_title(text="Policy", prov=_prov(1, "Policy"))
    document.add_heading(text="III. Scope", level=1, prov=_prov(1, "III. Scope"))
    document.add_heading(text="III.1 Detail", level=2, prov=_prov(1, "III.1 Detail"))
    for index in range(4):
        document.add_text(
            label=DocItemLabel.TEXT,
            text=f"Paragraph {index} stays together.",
            prov=_prov(1),
        )
    document.add_heading(text="IV. Next", level=1, prov=_prov(1, "IV. Next"))
    document.add_text(label=DocItemLabel.TEXT, text="Only the next section.", prov=_prov(1))

    chunks, prepared = _chunks(document)

    assert prepared.structure == "headed"
    first = chunks[0]
    assert first.element_type == "text"
    assert first.structure == "headed"
    assert first.section_path == ("Policy", "III. Scope", "III.1 Detail")
    assert first.heading == "III.1 Detail"
    assert first.text == (
        "Policy\nIII. Scope\nIII.1 Detail\n"
        "Paragraph 0 stays together.\n"
        "Paragraph 1 stays together.\n"
        "Paragraph 2 stays together.\n"
        "Paragraph 3 stays together."
    )
    assert all("Paragraph 0" not in chunk.text for chunk in chunks[1:])
    assert chunks[1].section_path == ("Policy", "IV. Next")
    assert "Only the next section." in chunks[1].text
    assert not chunks[1].text.startswith("Paragraph 3 stays together.")


def test_level_one_headings_do_not_invent_parents() -> None:
    document = _document("levels.pdf")
    document.add_heading(text="Alpha", level=1, prov=_prov(1, "Alpha"))
    document.add_text(label=DocItemLabel.TEXT, text="Body A.", prov=_prov(1))
    document.add_heading(text="Beta", level=1, prov=_prov(1, "Beta"))
    document.add_text(label=DocItemLabel.TEXT, text="Body B.", prov=_prov(1))

    chunks, _prepared = _chunks(document)

    assert [chunk.section_path for chunk in chunks] == [("Alpha",), ("Beta",)]
    assert [chunk.heading for chunk in chunks] == ["Alpha", "Beta"]


def test_list_items_that_fit_stay_together() -> None:
    document = _document("list.pdf")
    document.add_heading(text="Items", level=1, prov=_prov(1, "Items"))
    document.add_list_item(text="one", prov=_prov(1))
    document.add_list_item(text="two", prov=_prov(1))

    chunks, _prepared = _chunks(document)

    assert len(chunks) == 1
    assert chunks[0].element_type == "list"
    assert "one" in chunks[0].text
    assert "two" in chunks[0].text


def test_flat_short_text_has_no_path_filename_or_overlap() -> None:
    document = _document("notes.pdf")
    document.add_text(label=DocItemLabel.TEXT, text="A single short body.", prov=_prov(1))

    chunks, prepared = _chunks(document)

    assert prepared.structure == "flat"
    assert len(chunks) == 1
    assert chunks[0].section_path == ()
    assert chunks[0].heading is None
    assert chunks[0].structure == "flat"
    assert chunks[0].text == "A single short body."
    assert "notes.pdf" not in chunks[0].text


def test_flat_cut_overlaps_the_last_sentence() -> None:
    sentence = "This is a complete sentence about policy terms. "
    body = sentence * 80
    encoding = tiktoken.get_encoding("cl100k_base")
    assert len(encoding.encode(body)) > 512
    document = _document("flat.pdf")
    document.add_text(label=DocItemLabel.TEXT, text=body, prov=_prov(1, body))

    chunks, prepared = _chunks(document)

    assert prepared.structure == "flat"
    assert len(chunks) >= 2
    assert all(chunk.section_path == () for chunk in chunks)
    assert "flat.pdf" not in chunks[1].text
    last = max(chunks[0].text.rfind("."), chunks[0].text.rfind("!"), chunks[0].text.rfind("?"))
    previous = max(
        chunks[0].text.rfind(".", 0, last),
        chunks[0].text.rfind("!", 0, last),
        chunks[0].text.rfind("?", 0, last),
    )
    expected = chunks[0].text[previous + 1 :].strip()
    assert chunks[1].text.startswith(expected)


def test_letterhead_on_most_pages_leaves_the_path() -> None:
    document = _document("letter.pdf", pages=4)
    for page in (1, 2, 3):
        document.add_heading(text="ACME Corp", level=1, prov=_prov(page, "ACME Corp"))
    document.add_heading(text="Terms", level=1, prov=_prov(1, "Terms"))
    document.add_text(label=DocItemLabel.TEXT, text="The real clause.", prov=_prov(1))

    chunks, prepared = _chunks(document)

    assert prepared.structure == "headed"
    assert all("ACME Corp" not in chunk.section_path for chunk in chunks)
    assert any(chunk.section_path == ("Terms",) for chunk in chunks)

    only_letterhead = _document("banner.pdf", pages=4)
    for page in (1, 2, 3, 4):
        only_letterhead.add_heading(text="ACME Corp", level=1, prov=_prov(page, "ACME Corp"))
    only_letterhead.add_text(label=DocItemLabel.TEXT, text="Body only.", prov=_prov(1))
    flat_chunks, flat = _chunks(only_letterhead)
    assert flat.structure == "flat"
    assert flat_chunks[0].section_path == ()
    assert "ACME Corp" not in flat_chunks[0].text

    counted = _document("counted.pdf", pages=4)
    for page in (1, 2, 3):
        counted.add_heading(text="ACME Corp", level=1, prov=_prov(page, "ACME Corp"))
    counted.add_text(label=DocItemLabel.TEXT, text="Banner clause.", prov=_prov(1))
    counted.add_heading(text="Terms", level=1, prov=_prov(1, "Terms"))
    counted.add_text(label=DocItemLabel.TEXT, text="The real clause.", prov=_prov(1))
    kept = prepare_document(counted, page_count=8)
    kept_chunks = chunk_document(counted, kept.structure, kept.table_notes)
    assert kept.structure == "headed"
    assert any("ACME Corp" in chunk.section_path for chunk in kept_chunks)


def test_table_is_its_own_chunk_with_caption_first() -> None:
    document = _document("fees.pdf")
    document.add_text(
        label=DocItemLabel.TEXT,
        text="See the fees. Keep this sentence.",
        prov=_prov(1),
    )
    caption = document.add_text(label=DocItemLabel.CAPTION, text="Fees table.", prov=_prov(1))
    cell = TableCell(
        text="42",
        start_row_offset_idx=0,
        end_row_offset_idx=1,
        start_col_offset_idx=0,
        end_col_offset_idx=1,
    )
    document.add_table(
        data=TableData(num_rows=1, num_cols=1, table_cells=[cell]),
        caption=caption,
        prov=_prov(1),
    )
    document.add_text(label=DocItemLabel.TEXT, text="After the table.", prov=_prov(1))

    chunks, _prepared = _chunks(document)

    tables = [chunk for chunk in chunks if chunk.element_type == "table"]
    assert len(tables) == 1
    assert tables[0].text.startswith("Fees table")
    assert not tables[0].text.startswith("Keep this sentence.")
    assert "42" in tables[0].text
    assert not any(chunk.text.strip() == "Fees table." for chunk in chunks)
    neighbors = [chunk for chunk in chunks if "After the table." in chunk.text]
    assert len(neighbors) == 1
    assert neighbors[0].element_type != "table"
    assert not neighbors[0].text.startswith("Fees table.")


def test_linked_footnote_is_kept_and_orphan_is_dropped() -> None:
    document = _document("notes.pdf")
    paragraph = document.add_text(label=DocItemLabel.TEXT, text="See the note.", prov=_prov(1))
    document.add_text(
        label=DocItemLabel.FOOTNOTE,
        text="Linked note text.",
        prov=_prov(1),
        parent=paragraph,
    )
    document.add_text(label=DocItemLabel.FOOTNOTE, text="Orphan note text.", prov=_prov(1))
    caption = document.add_text(label=DocItemLabel.CAPTION, text="Rates", prov=_prov(1))
    cell = TableCell(
        text="9",
        start_row_offset_idx=0,
        end_row_offset_idx=1,
        start_col_offset_idx=0,
        end_col_offset_idx=1,
    )
    table = document.add_table(
        data=TableData(num_rows=1, num_cols=1, table_cells=[cell]),
        caption=caption,
        prov=_prov(1),
    )
    footnote = document.add_text(label=DocItemLabel.FOOTNOTE, text="Table note.", prov=_prov(1))
    table.footnotes.append(RefItem(cref=footnote.self_ref))

    chunks, _prepared = _chunks(document)
    joined = "\n".join(chunk.text for chunk in chunks)

    paragraph_chunk = next(chunk for chunk in chunks if "See the note." in chunk.text)
    assert paragraph_chunk.text.endswith("Linked note text.")
    table_chunk = next(chunk for chunk in chunks if chunk.element_type == "table")
    assert table_chunk.text.endswith("Table note.")
    assert "Orphan note text." not in joined
    assert DocItemLabel.FOOTNOTE.value not in _labels(document)


def test_discarded_labels_do_not_reach_the_chunker() -> None:
    document = _document("furniture.pdf")
    document.add_text(label=DocItemLabel.PAGE_HEADER, text="SECRET HEADER", prov=_prov(1))
    document.add_text(label=DocItemLabel.TEXT, text="Visible body.", prov=_prov(1))
    document.add_text(label=DocItemLabel.PAGE_FOOTER, text="SECRET FOOTER", prov=_prov(1))
    document.add_text(label=DocItemLabel.REFERENCE, text="SECRET REFERENCE", prov=_prov(1))
    document.add_text(label=DocItemLabel.MARKER, text="SECRET MARKER", prov=_prov(1))
    document.add_text(label=DocItemLabel.EMPTY_VALUE, text=" ", prov=_prov(1))
    document.add_text(label=DocItemLabel.HANDWRITTEN_TEXT, text="SECRET INK", prov=_prov(1))
    document.add_text(label=DocItemLabel.FIELD_HINT, text="SECRET HINT", prov=_prov(1))
    caption = document.add_text(label=DocItemLabel.CAPTION, text="Figure caption.", prov=_prov(1))
    document.add_picture(caption=caption, prov=_prov(1))
    cell = TableCell(
        text="index",
        start_row_offset_idx=0,
        end_row_offset_idx=1,
        start_col_offset_idx=0,
        end_col_offset_idx=1,
    )
    document.add_table(
        data=TableData(num_rows=1, num_cols=1, table_cells=[cell]),
        label=DocItemLabel.DOCUMENT_INDEX,
        prov=_prov(1),
    )
    region = document.add_field_region(prov=_prov(1))
    document.add_text(
        label=DocItemLabel.TEXT,
        text="Kept field text.",
        prov=_prov(1),
        parent=region,
    )
    document.add_text(label=DocItemLabel.CHECKBOX_SELECTED, text="Chosen", prov=_prov(1))

    prepared = prepare_document(document)
    labels = _labels(document)

    assert prepared.structure == "flat"
    for label in (
        "page_header",
        "page_footer",
        "document_index",
        "reference",
        "marker",
        "empty_value",
        "handwritten_text",
        "field_hint",
        "picture",
        "field_region",
        "checkbox_selected",
    ):
        assert label not in labels
    chunks = chunk_document(document, prepared.structure, prepared.table_notes)
    joined = "\n".join(chunk.text for chunk in chunks)
    assert "Visible body." in joined
    assert "Kept field text." in joined
    assert "Figure caption." in joined
    assert joined.index("Figure caption.") < joined.index("Kept field text.")
    assert "Chosen" in joined
    assert "SECRET" not in joined

    checkbox_only = _document("check.pdf")
    checkbox_only.add_text(label=DocItemLabel.CHECKBOX_SELECTED, text="Chosen", prov=_prov(1))
    checkbox_chunks, _prepared = _chunks(checkbox_only)
    assert checkbox_chunks[0].element_type == "list"
    assert "Chosen" in checkbox_chunks[0].text


def test_page_numbers_are_zero_based_and_page_end_spans() -> None:
    document = _document("span.pdf", pages=4)
    document.add_text(label=DocItemLabel.TEXT, text="Starts on page two.", prov=_prov(2))
    document.add_text(label=DocItemLabel.TEXT, text="Ends on page four.", prov=_prov(4))

    chunks, _prepared = _chunks(document)

    assert len(chunks) == 1
    assert chunks[0].page == 1
    assert chunks[0].page_end == 3


def test_pipeline_chunks_the_document_from_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.ingestion import docling_pipeline

    document = _document("policy.pdf")
    document.add_title(text="Policy", prov=_prov(1, "Policy"))
    document.add_text(label=DocItemLabel.TEXT, text="The clause.", prov=_prov(1))

    def _fake_convert(content: bytes) -> tuple[DoclingDocument, int]:
        assert content == b"%PDF"
        return document, 1

    monkeypatch.setattr(docling_pipeline, "_convert_pdf", _fake_convert)
    pipeline = docling_pipeline.DoclingPdfPipeline()
    extracted = pipeline.extract(b"%PDF")
    chunks = pipeline.chunk(extracted)

    assert extracted.page_count == 1
    assert chunks[0].section_path == ("Policy",)
    assert "The clause." in chunks[0].text

    other = docling_pipeline.DoclingPdfPipeline()
    with pytest.raises(RuntimeError, match="extract before chunk"):
        other.chunk(extracted)
