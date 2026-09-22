from __future__ import annotations

from uuid import UUID, uuid5

import pytest

from app.application.documents.process_document import ProcessDocument, ProcessOutcome
from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.errors import TenantIsolationError
from app.domain.ports.ingestion import PageText
from app.domain.tenancy import TenantId
from app.infrastructure.ingestion.page_chunker import PageAwareChunker
from app.infrastructure.ingestion.qdrant_chunk_store import chunk_point_id
from tests.fakes import (
    FakeEmbeddingGenerator,
    FakePdfTextExtractor,
    InMemoryChunkStore,
    InMemoryDocumentBytes,
    InMemoryDocumentRepository,
)

_NAMESPACE = UUID("8b3e1c4a-6f2d-4a7e-9c1b-2d5e6f708192")
_ACTOR = Actor(tenant_id="t1", user_id="u1")


def _process(
    *,
    documents: InMemoryDocumentRepository | None = None,
    bytes_store: InMemoryDocumentBytes | None = None,
    extractor: FakePdfTextExtractor | None = None,
    embeddings: FakeEmbeddingGenerator | None = None,
    chunk_store: InMemoryChunkStore | None = None,
    max_pages: int = 100,
    max_concurrent: int = 2,
    commit_log: list[str] | None = None,
) -> tuple[
    ProcessDocument,
    InMemoryDocumentRepository,
    InMemoryDocumentBytes,
    FakeEmbeddingGenerator,
    InMemoryChunkStore,
]:
    docs = documents or InMemoryDocumentRepository()
    store = bytes_store or InMemoryDocumentBytes()
    emb = embeddings or FakeEmbeddingGenerator()
    chunks = chunk_store or InMemoryChunkStore()
    log = commit_log if commit_log is not None else []

    def commit() -> None:
        log.append("commit")
        if docs.get("doc-1") is not None:
            emb.committed_before_embed = (
                docs.get("doc-1").status is DocumentStatus.PROCESSING  # type: ignore[union-attr]
            )

    use_case = ProcessDocument(
        docs,
        store,
        extractor or FakePdfTextExtractor(),
        PageAwareChunker(),
        emb,
        chunks,
        max_pages=max_pages,
        max_concurrent=max_concurrent,
        commit=commit,
    )
    return use_case, docs, store, emb, chunks


def _pending_doc(
    documents: InMemoryDocumentRepository,
    bytes_store: InMemoryDocumentBytes,
    *,
    document_id: str = "doc-1",
    tenant_id: str = "t1",
    text: str = "hello world",
) -> Document:
    document = Document(
        id=document_id,
        tenant_id=TenantId(tenant_id),
        filename="handbook.pdf",
        status=DocumentStatus.PENDING,
    )
    documents.save(document)
    bytes_store.put(
        tenant_id=tenant_id,
        document_id=document_id,
        filename="handbook.pdf",
        content=b"%PDF-1.4",
    )
    return document


def test_ingest_ready_with_payload_and_uuid5() -> None:
    commit_log: list[str] = []
    use_case, documents, bytes_store, embeddings, chunk_store = _process(commit_log=commit_log)
    _pending_doc(documents, bytes_store)
    chunk_store.points["doc-1:9"] = {
        "tenant_id": "t1",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 9,
        "text": "stale",
        "vector": [9.0],
    }
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.READY
    assert documents.get("doc-1").status is DocumentStatus.READY  # type: ignore[union-attr]
    assert commit_log == ["commit"]
    assert embeddings.committed_before_embed is True
    assert embeddings.calls == 1
    assert chunk_store.upsert_calls == 1
    assert "doc-1:9" not in chunk_store.points
    point = chunk_store.points["doc-1:0"]
    assert point["tenant_id"] == "t1"
    assert point["document_id"] == "doc-1"
    assert point["filename"] == "handbook.pdf"
    assert point["page"] == 0
    assert point["chunk_index"] == 0
    assert point["text"] == "hello world"
    assert chunk_point_id("doc-1", 0) == str(uuid5(_NAMESPACE, "doc-1:0"))


def test_too_many_pages_fails_and_clears_points() -> None:
    pages = [PageText(page=i, text=f"page {i}") for i in range(3)]
    use_case, documents, bytes_store, _, chunk_store = _process(
        extractor=FakePdfTextExtractor(pages),
        max_pages=2,
    )
    _pending_doc(documents, bytes_store)
    chunk_store.points["doc-1:0"] = {
        "tenant_id": "t1",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 0,
        "text": "old",
        "vector": [1.0],
    }
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.FAILED
    assert documents.get("doc-1").status is DocumentStatus.FAILED  # type: ignore[union-attr]
    assert chunk_store.points == {}
    assert chunk_store.upsert_calls == 0


def test_extract_fails_or_no_chunks() -> None:
    use_case, documents, bytes_store, _, chunk_store = _process(
        extractor=FakePdfTextExtractor(fail=True),
    )
    _pending_doc(documents, bytes_store)
    assert use_case.execute(_ACTOR, "doc-1") is ProcessOutcome.FAILED
    assert documents.get("doc-1").status is DocumentStatus.FAILED  # type: ignore[union-attr]
    assert chunk_store.points == {}

    use_case, documents, bytes_store, _, chunk_store = _process(
        extractor=FakePdfTextExtractor([PageText(page=0, text="   ")]),
    )
    _pending_doc(documents, bytes_store)
    assert use_case.execute(_ACTOR, "doc-1") is ProcessOutcome.FAILED
    assert documents.get("doc-1").status is DocumentStatus.FAILED  # type: ignore[union-attr]
    assert chunk_store.upsert_calls == 0


def test_at_capacity_stays_pending_deferred() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    for index in range(2):
        documents.save(
            Document(
                id=f"busy-{index}",
                tenant_id=TenantId("t1"),
                filename="x.pdf",
                status=DocumentStatus.PROCESSING,
            )
        )
    use_case, _, _, embeddings, chunk_store = _process(
        documents=documents,
        bytes_store=bytes_store,
    )
    _pending_doc(documents, bytes_store)
    extractor = FakePdfTextExtractor()
    use_case = ProcessDocument(
        documents,
        bytes_store,
        extractor,
        PageAwareChunker(),
        embeddings,
        chunk_store,
        max_pages=100,
        max_concurrent=2,
    )
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.DEFERRED
    assert documents.get("doc-1").status is DocumentStatus.PENDING  # type: ignore[union-attr]
    assert extractor.calls == 0
    assert chunk_store.upsert_calls == 0


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.PROCESSING, DocumentStatus.READY, DocumentStatus.FAILED],
)
def test_duplicate_job_skips(status: DocumentStatus) -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=status,
        )
    )
    use_case, _, _, embeddings, chunk_store = _process(
        documents=documents,
        bytes_store=bytes_store,
    )
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.SKIPPED
    assert documents.get("doc-1").status is status  # type: ignore[union-attr]
    assert embeddings.calls == 0
    assert chunk_store.upsert_calls == 0


def test_other_tenant_job_raises_isolation() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    _pending_doc(documents, bytes_store, tenant_id="t2")
    use_case, _, _, _, _ = _process(documents=documents, bytes_store=bytes_store)
    with pytest.raises(TenantIsolationError):
        use_case.execute(_ACTOR, "doc-1")
    assert documents.get("doc-1").status is DocumentStatus.PENDING  # type: ignore[union-attr]


def test_deleted_before_finish_skips() -> None:
    use_case, documents, bytes_store, _, chunk_store = _process()
    outcome = use_case.execute(_ACTOR, "missing")
    assert outcome is ProcessOutcome.SKIPPED
    assert documents.items == []
    assert chunk_store.upsert_calls == 0


def test_deleted_after_claim_does_not_upsert() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    _pending_doc(documents, bytes_store)
    chunk_store = InMemoryChunkStore()

    class DropOnEmbed:
        def embed(self, texts: list[str]) -> list[list[float]]:
            documents.delete("doc-1")
            return [[1.0, 1.0, 1.0] for _ in texts]

    use_case = ProcessDocument(
        documents,
        bytes_store,
        FakePdfTextExtractor(),
        PageAwareChunker(),
        DropOnEmbed(),
        chunk_store,
        max_pages=100,
        max_concurrent=2,
        commit=lambda: None,
    )
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.SKIPPED
    assert documents.get("doc-1") is None
    assert chunk_store.upsert_calls == 0


def test_embed_failure_clears_points() -> None:
    use_case, documents, bytes_store, _, chunk_store = _process(
        embeddings=FakeEmbeddingGenerator(fail=True),
    )
    _pending_doc(documents, bytes_store)
    chunk_store.points["doc-1:9"] = {
        "tenant_id": "t1",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 9,
        "text": "old",
        "vector": [1.0],
    }
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.FAILED
    assert documents.get("doc-1").status is DocumentStatus.FAILED  # type: ignore[union-attr]
    assert chunk_store.points == {}


def test_upsert_failure_ends_failed_with_no_points() -> None:
    use_case, documents, bytes_store, _, chunk_store = _process(
        chunk_store=InMemoryChunkStore(fail_upsert=True),
    )
    _pending_doc(documents, bytes_store)
    chunk_store.points["doc-1:3"] = {
        "tenant_id": "t1",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 3,
        "text": "old",
        "vector": [1.0],
    }
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.FAILED
    assert documents.get("doc-1").status is DocumentStatus.FAILED  # type: ignore[union-attr]
    assert chunk_store.points == {}


def test_blank_pages_still_count_toward_page_limit() -> None:
    pages = [PageText(page=i, text="   ") for i in range(3)]
    use_case, documents, bytes_store, _, chunk_store = _process(
        extractor=FakePdfTextExtractor(pages),
        max_pages=2,
    )
    _pending_doc(documents, bytes_store)
    outcome = use_case.execute(_ACTOR, "doc-1")
    assert outcome is ProcessOutcome.FAILED
    assert documents.get("doc-1").status is DocumentStatus.FAILED  # type: ignore[union-attr]
    assert chunk_store.upsert_calls == 0
    assert chunk_store.points == {}


def test_real_chunker_splits_on_whitespace_and_skips_blank_pages() -> None:
    long = "word " * 300
    pages = [
        PageText(page=0, text=long),
        PageText(page=1, text="   "),
        PageText(page=2, text="short"),
    ]
    chunks = PageAwareChunker().chunk_pages(pages)
    assert all(len(chunk.text) <= 1000 for chunk in chunks)
    assert chunks[-1].text == "short"
    assert chunks[-1].page == 2
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert not any(chunk.page == 1 for chunk in chunks)


def test_real_chunker_hard_cuts_page_with_no_spaces() -> None:
    chunks = PageAwareChunker().chunk_pages([PageText(page=0, text="a" * 1500)])
    assert len(chunks[0].text) == 1000
    assert chunks[0].text == "a" * 1000
    assert chunks[1].text == "a" * 500
