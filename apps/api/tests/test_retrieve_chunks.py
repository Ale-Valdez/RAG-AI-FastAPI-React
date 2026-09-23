from __future__ import annotations

import math

import pytest

from app.application.retrieval.retrieve_chunks import RetrieveChunks
from app.bootstrap.create_app import create_app
from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.errors import NotFoundError
from app.domain.tenancy import TenantId
from app.infrastructure.config.settings import Settings
from tests.fakes import FakeEmbeddingGenerator, InMemoryChunkStore, InMemoryDocumentRepository

_ACTOR_A = Actor(tenant_id="tenant-a", user_id="user-a")
_QUESTION = "what is the policy?"


def _use_case(
    documents: InMemoryDocumentRepository,
    embeddings: FakeEmbeddingGenerator,
    chunk_store: InMemoryChunkStore,
    *,
    top_k: int = 5,
    score_threshold: float = 0.70,
) -> RetrieveChunks:
    return RetrieveChunks(
        documents,
        embeddings,
        chunk_store,
        top_k=top_k,
        score_threshold=score_threshold,
    )


def _save(
    documents: InMemoryDocumentRepository,
    document_id: str,
    tenant_id: str,
    status: DocumentStatus,
) -> None:
    documents.save(
        Document(
            id=document_id,
            tenant_id=TenantId(tenant_id),
            filename=f"{document_id}.pdf",
            status=status,
        )
    )


def _point(
    chunk_store: InMemoryChunkStore,
    *,
    tenant_id: str,
    document_id: str,
    chunk_index: int,
    vector: list[float],
    text: str | None = None,
    page: int = 0,
) -> None:
    chunk_store.points[f"{document_id}:{chunk_index}"] = {
        "tenant_id": tenant_id,
        "document_id": document_id,
        "filename": f"{document_id}.pdf",
        "page": page,
        "chunk_index": chunk_index,
        "text": text if text is not None else f"{document_id}:{chunk_index}",
        "vector": vector,
    }


def test_corpus_search_returns_only_actor_ready_chunks_within_defaults() -> None:
    settings = Settings()
    assert settings.rag_top_k == 5
    assert settings.rag_score_threshold == 0.70
    assert settings.openai_embed_model == "text-embedding-3-small"

    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _save(documents, "ready-2", "tenant-a", DocumentStatus.READY)
    _save(documents, "pending-a", "tenant-a", DocumentStatus.PENDING)
    _save(documents, "ready-b", "tenant-b", DocumentStatus.READY)

    for index in range(4):
        _point(
            chunk_store,
            tenant_id="tenant-a",
            document_id="ready-1",
            chunk_index=index,
            vector=[1.0, 1.0, 1.0],
            page=index,
        )
    for index in range(2):
        _point(
            chunk_store,
            tenant_id="tenant-a",
            document_id="ready-2",
            chunk_index=index,
            vector=[1.0, 1.0, 1.0],
        )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=9,
        vector=[1.0, 0.0, 0.0],
        text="below threshold",
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="pending-a",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="not ready",
    )
    _point(
        chunk_store,
        tenant_id="tenant-b",
        document_id="ready-b",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="other tenant",
    )

    hits = _use_case(
        documents,
        embeddings,
        chunk_store,
        top_k=settings.rag_top_k,
        score_threshold=settings.rag_score_threshold,
    ).execute(_ACTOR_A, _QUESTION)

    assert len(hits) == 5
    assert {hit.document_id for hit in hits} <= {"ready-1", "ready-2"}
    assert all(hit.score >= 0.70 for hit in hits)
    assert all(hit.text not in {"below threshold", "not ready", "other tenant"} for hit in hits)
    assert hits == sorted(hits, key=lambda hit: (-hit.score, hit.document_id, hit.chunk_index))
    assert embeddings.texts == [[_QUESTION]]
    assert len(chunk_store.search_calls) == 1
    call = chunk_store.search_calls[0]
    actor = call["actor"]
    assert isinstance(actor, Actor)
    assert actor.tenant_id == "tenant-a"
    assert call["document_id"] is None
    assert call["ready_ids"] == ["ready-2", "ready-1"]
    assert call["top_k"] == 5
    assert call["score_threshold"] == 0.70
    assert call["query_vector"] == [1.0, 1.0, 1.0]


def test_one_document_limits_hits_and_keeps_tenant_filter() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _save(documents, "ready-2", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="from one",
        page=3,
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-2",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="from two",
    )
    _point(
        chunk_store,
        tenant_id="tenant-b",
        document_id="ready-1",
        chunk_index=1,
        vector=[1.0, 1.0, 1.0],
        text="same id other tenant",
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(
        _ACTOR_A,
        _QUESTION,
        "ready-1",
    )

    assert len(hits) == 1
    assert hits[0].document_id == "ready-1"
    assert hits[0].filename == "ready-1.pdf"
    assert hits[0].page == 3
    assert hits[0].chunk_index == 0
    assert hits[0].text == "from one"
    assert hits[0].score >= 0.70
    call = chunk_store.search_calls[0]
    actor = call["actor"]
    assert isinstance(actor, Actor)
    assert actor.tenant_id == "tenant-a"
    assert call["document_id"] == "ready-1"
    assert call["ready_ids"] == ["ready-1"]


def test_low_scores_return_empty() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, _QUESTION)

    assert hits == []
    assert len(chunk_store.search_calls) == 1


def test_score_equal_to_threshold_is_returned() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[1.0, 0.0])
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[0.7, math.sqrt(1 - 0.49)],
        text="on threshold",
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, _QUESTION)

    assert len(hits) == 1
    assert hits[0].text == "on threshold"
    assert hits[0].score == pytest.approx(0.70)


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.PENDING, DocumentStatus.PROCESSING, DocumentStatus.FAILED],
)
def test_no_ready_documents_does_not_query_vector_store(status: DocumentStatus) -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    _save(documents, "doc-1", "tenant-a", status)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="doc-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, _QUESTION)

    assert hits == []
    assert chunk_store.search_calls == []
    assert embeddings.calls == 0


def test_no_ready_mix_does_not_query_vector_store() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    for document_id, status in (
        ("pending-doc", DocumentStatus.PENDING),
        ("processing-doc", DocumentStatus.PROCESSING),
        ("failed-doc", DocumentStatus.FAILED),
    ):
        _save(documents, document_id, "tenant-a", status)
        _point(
            chunk_store,
            tenant_id="tenant-a",
            document_id=document_id,
            chunk_index=0,
            vector=[1.0, 1.0, 1.0],
        )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, _QUESTION)

    assert hits == []
    assert chunk_store.search_calls == []
    assert embeddings.calls == 0


@pytest.mark.parametrize(
    ("document_id", "tenant_id", "status"),
    [
        ("missing", "tenant-a", None),
        ("other-tenant", "tenant-b", DocumentStatus.READY),
        ("pending-doc", "tenant-a", DocumentStatus.PENDING),
        ("processing-doc", "tenant-a", DocumentStatus.PROCESSING),
        ("failed-doc", "tenant-a", DocumentStatus.FAILED),
    ],
)
def test_bad_document_id_raises_not_found_without_search(
    document_id: str,
    tenant_id: str,
    status: DocumentStatus | None,
) -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    if status is not None:
        _save(documents, document_id, tenant_id, status)
        _point(
            chunk_store,
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_index=0,
            vector=[1.0, 1.0, 1.0],
        )

    with pytest.raises(NotFoundError):
        _use_case(documents, embeddings, chunk_store).execute(
            _ACTOR_A,
            _QUESTION,
            document_id,
        )

    assert chunk_store.search_calls == []
    assert embeddings.calls == 0


def test_retrieval_adds_no_chat_route() -> None:
    application = create_app(
        settings=Settings(jwt_secret="test-secret-key-at-least-32-bytes!!"),
        readiness_probes=[],
    )
    paths = [getattr(route, "path", "") for route in application.routes]
    assert paths
    assert all("chat" not in path and "conversation" not in path for path in paths)
