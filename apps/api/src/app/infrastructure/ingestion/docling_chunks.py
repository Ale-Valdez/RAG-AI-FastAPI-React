from __future__ import annotations

from dataclasses import dataclass, field

import tiktoken
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import (
    DocItem,
    DoclingDocument,
    SectionHeaderItem,
    TableItem,
    TextItem,
    TitleItem,
)
from docling_core.types.doc.items.node import FloatingItem, NodeItem
from docling_core.types.doc.labels import DocItemLabel

from app.domain.ports.ingestion import (
    BlockKind,
    ContentBlock,
    DocumentStructure,
    ElementType,
    TextChunk,
)

_MAX_TOKENS = 512
_LAYERS = set(ContentLayer)
_HEADINGS = {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
_DISCARD = {
    DocItemLabel.PAGE_HEADER,
    DocItemLabel.PAGE_FOOTER,
    DocItemLabel.DOCUMENT_INDEX,
    DocItemLabel.REFERENCE,
    DocItemLabel.HANDWRITTEN_TEXT,
    DocItemLabel.MARKER,
    DocItemLabel.EMPTY_VALUE,
    DocItemLabel.FIELD_HINT,
    DocItemLabel.PICTURE,
    DocItemLabel.CHART,
    DocItemLabel.PARAGRAPH,
    DocItemLabel.FIELD_KEY,
    DocItemLabel.FIELD_VALUE,
    DocItemLabel.FIELD_HEADING,
}
_CONTAINERS = {
    DocItemLabel.FORM,
    DocItemLabel.KEY_VALUE_REGION,
    DocItemLabel.FIELD_REGION,
    DocItemLabel.FIELD_ITEM,
}
_LIST_LABELS = {
    DocItemLabel.CHECKBOX_SELECTED,
    DocItemLabel.CHECKBOX_UNSELECTED,
    DocItemLabel.GRADING_SCALE,
}
_BLOCK_KINDS: dict[DocItemLabel, BlockKind] = {
    DocItemLabel.TITLE: "title",
    DocItemLabel.SECTION_HEADER: "section_header",
    DocItemLabel.TEXT: "text",
    DocItemLabel.LIST_ITEM: "list_item",
    DocItemLabel.TABLE: "table",
    DocItemLabel.CODE: "code",
    DocItemLabel.FORMULA: "formula",
}


@dataclass
class PreparedDocument:
    structure: DocumentStructure
    table_notes: dict[str, str] = field(default_factory=dict)


def prepare_document(
    document: DoclingDocument,
    *,
    page_count: int | None = None,
) -> PreparedDocument:
    document._migrate_furniture_to_body()
    notes = _attach_footnotes(document)
    _release_picture_captions(document)
    _unwrap_containers(document)
    _rewrite_as_list_items(document)
    _delete_labels(document, _DISCARD | _CONTAINERS | _LIST_LABELS | {DocItemLabel.FOOTNOTE})
    _drop_letterhead(document, page_count if page_count is not None else len(document.pages))
    structure: DocumentStructure = "headed" if _has_heading(document) else "flat"
    return PreparedDocument(structure=structure, table_notes=notes)


def chunk_document(
    document: DoclingDocument,
    structure: DocumentStructure,
    table_notes: dict[str, str] | None = None,
) -> list[TextChunk]:
    notes = table_notes or {}
    chunker = _chunker()
    raw = list(HybridChunker(tokenizer=chunker.tokenizer, merge_peers=False).chunk(document))
    grouped = _merge_keeping_tables(chunker, raw)
    chunks: list[TextChunk] = []
    for doc_chunk in grouped:
        text = chunker.contextualize(doc_chunk)
        element_type = _element_type(doc_chunk.meta.doc_items)
        if element_type == "table":
            suffix = _table_suffix(doc_chunk.meta.doc_items, notes)
            if suffix:
                text = f"{text}\n{suffix}"
        path = () if structure == "flat" else tuple(doc_chunk.meta.headings or ())
        page, page_end = _pages(doc_chunk.meta.doc_items)
        chunks.append(
            TextChunk(
                page=page,
                chunk_index=len(chunks),
                text=text,
                section_path=path,
                heading=path[-1] if path else None,
                page_end=page_end,
                element_type=element_type,
                structure=structure,
            )
        )
    if structure == "flat":
        _overlap_flat_cuts(chunks)
    return chunks


def content_blocks(document: DoclingDocument) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    for item, _level in _iter_nodes(document):
        if not isinstance(item, DocItem):
            continue
        kind = _BLOCK_KINDS.get(item.label)
        if kind is None:
            continue
        text = _block_text(document, item)
        if not text.strip():
            continue
        level = item.level if isinstance(item, SectionHeaderItem) else None
        page, _page_end = _pages([item])
        blocks.append(ContentBlock(kind=kind, level=level, text=text, page=page))
    return blocks


def _chunker() -> HybridChunker:
    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.get_encoding("cl100k_base"),
        max_tokens=_MAX_TOKENS,
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


def _merge_keeping_tables(chunker: HybridChunker, raw: list[object]) -> list[object]:
    grouped: list[object] = []
    pending: list[object] = []

    def flush() -> None:
        if not pending:
            return
        grouped.extend(chunker._merge_chunks_with_matching_metadata(pending))
        pending.clear()

    for doc_chunk in raw:
        if _is_table_chunk(doc_chunk):
            flush()
            grouped.append(doc_chunk)
            continue
        pending.append(doc_chunk)
    flush()
    return grouped


def _is_table(item: DocItem) -> bool:
    return item.label == DocItemLabel.TABLE


def _is_table_chunk(doc_chunk: object) -> bool:
    items = doc_chunk.meta.doc_items  # type: ignore[attr-defined]
    return any(_is_table(item) for item in items)


def _element_type(items: list[DocItem]) -> ElementType:
    if any(_is_table(item) for item in items):
        return "table"
    if items and all(item.label == DocItemLabel.LIST_ITEM for item in items):
        return "list"
    return "text"


def _table_suffix(items: list[DocItem], notes: dict[str, str]) -> str:
    parts = [notes[item.self_ref] for item in items if item.self_ref in notes]
    return "\n".join(part for part in parts if part)


def _pages(items: list[DocItem]) -> tuple[int, int]:
    numbers = [
        prov.page_no - 1
        for item in items
        for prov in getattr(item, "prov", []) or []
        if prov.page_no >= 1
    ]
    if not numbers:
        return 0, 0
    return min(numbers), max(numbers)


def _overlap_flat_cuts(chunks: list[TextChunk]) -> None:
    for index, chunk in enumerate(chunks[:-1]):
        nxt = chunks[index + 1]
        if chunk.element_type == "table" or nxt.element_type == "table":
            continue
        if chunk.element_type not in {"text", "list"} or nxt.element_type not in {"text", "list"}:
            continue
        sentence = _last_sentence(chunk.text)
        if sentence is None or nxt.text.startswith(sentence):
            continue
        nxt_text = f"{sentence}\n{nxt.text}"
        chunks[index + 1] = TextChunk(
            page=nxt.page,
            chunk_index=nxt.chunk_index,
            text=nxt_text,
            section_path=nxt.section_path,
            heading=nxt.heading,
            page_end=nxt.page_end,
            element_type=nxt.element_type,
            structure=nxt.structure,
        )


def _last_sentence(text: str) -> str | None:
    last = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
    if last < 0:
        return None
    previous = max(
        text.rfind(".", 0, last),
        text.rfind("!", 0, last),
        text.rfind("?", 0, last),
    )
    start = 0 if previous < 0 else previous + 1
    sentence = text[start:].strip()
    return sentence or None


def _attach_footnotes(document: DoclingDocument) -> dict[str, str]:
    owners = _footnote_owners(document)
    notes: dict[str, str] = {}
    for item, _level in _iter_nodes(document):
        if not isinstance(item, TextItem) or item.label != DocItemLabel.FOOTNOTE:
            continue
        targets = owners.get(item.self_ref, [])
        if not targets:
            continue
        for target in targets:
            if isinstance(target, TextItem):
                target.text = f"{target.text.rstrip()}\n{item.text.strip()}"
            elif isinstance(target, TableItem):
                current = notes.get(target.self_ref, "")
                notes[target.self_ref] = "\n".join(
                    part for part in (current, item.text.strip()) if part
                )
    return notes


def _footnote_owners(document: DoclingDocument) -> dict[str, list[NodeItem]]:
    owners: dict[str, list[NodeItem]] = {}
    for item, _level in _iter_nodes(document):
        if isinstance(item, FloatingItem):
            for ref in item.footnotes:
                owners.setdefault(ref.cref, []).append(item)
        if isinstance(item, TextItem) and item.label == DocItemLabel.FOOTNOTE and item.parent is not None:
            parent = item.parent.resolve(document)
            if isinstance(parent, TextItem) and parent.label in {DocItemLabel.TEXT, DocItemLabel.LIST_ITEM}:
                owners.setdefault(item.self_ref, []).append(parent)
    return owners


def _release_picture_captions(document: DoclingDocument) -> None:
    pictures = [
        item
        for item, _level in _iter_nodes(document)
        if isinstance(item, DocItem) and item.label in {DocItemLabel.PICTURE, DocItemLabel.CHART}
    ]
    for picture in pictures:
        if picture.parent is None:
            continue
        parent = picture.parent.resolve(document)
        for ref in list(picture.captions):
            caption = ref.resolve(document)
            if not isinstance(caption, TextItem):
                continue
            document._move_subtree(
                old_subroot=caption,
                new_subroot=parent,
                pos=_child_index(parent, picture),
            )
            caption.label = DocItemLabel.TEXT  # type: ignore[assignment]


def _unwrap_containers(document: DoclingDocument) -> None:
    containers = [
        item
        for item, _level in _iter_nodes(document)
        if isinstance(item, DocItem) and item.label in _CONTAINERS
    ]
    for container in containers:
        if container.parent is None:
            continue
        parent = container.parent.resolve(document)
        position = _child_index(parent, container)
        for offset, ref in enumerate(list(container.children)):
            document._move_subtree(
                old_subroot=ref.resolve(document),
                new_subroot=parent,
                pos=position + offset,
            )


def _rewrite_as_list_items(document: DoclingDocument) -> None:
    items = [
        item
        for item, _level in _iter_nodes(document)
        if isinstance(item, TextItem) and item.label in _LIST_LABELS
    ]
    for item in items:
        document.insert_list_item(
            sibling=item,
            text=item.text,
            prov=item.prov[0] if item.prov else None,
            after=False,
        )


def _delete_labels(document: DoclingDocument, labels: set[DocItemLabel]) -> None:
    doomed = [
        item
        for item, _level in _iter_nodes(document)
        if isinstance(item, DocItem) and item.label in labels
    ]
    if doomed:
        document.delete_items(node_items=doomed)


def _drop_letterhead(document: DoclingDocument, page_count: int) -> None:
    if page_count < 2:
        return
    headings = [
        item
        for item, _level in _iter_nodes(document)
        if isinstance(item, (TitleItem, SectionHeaderItem))
    ]
    pages_by_text: dict[str, set[int]] = {}
    for item in headings:
        key = item.text.strip().casefold()
        if not key:
            continue
        pages_by_text.setdefault(key, set()).update(
            prov.page_no for prov in item.prov if prov.page_no >= 1
        )
    letterhead = {
        key
        for key, pages in pages_by_text.items()
        if len(pages) / page_count > 0.5
    }
    doomed = [item for item in headings if item.text.strip().casefold() in letterhead]
    if doomed:
        document.delete_items(node_items=doomed)


def _has_heading(document: DoclingDocument) -> bool:
    return any(
        isinstance(item, DocItem) and item.label in _HEADINGS
        for item, _level in _iter_nodes(document)
    )


def _iter_nodes(document: DoclingDocument):
    yield from document.iterate_items(
        with_groups=True,
        traverse_pictures=True,
        included_content_layers=_LAYERS,
    )


def _child_index(parent: NodeItem, child: NodeItem) -> int:
    ref = child.get_ref()
    for index, child_ref in enumerate(parent.children):
        if child_ref.cref == ref.cref:
            return index
    return len(parent.children)


def _block_text(document: DoclingDocument, item: DocItem) -> str:
    if isinstance(item, TableItem):
        return item.export_to_markdown(document)
    return getattr(item, "text", "")
