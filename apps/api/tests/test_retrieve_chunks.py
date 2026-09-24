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
    rewriter: object | None = None,
    reranker: object | None = None,
) -> RetrieveChunks:
    return RetrieveChunks(
        documents,
        embeddings,
        chunk_store,
        top_k=top_k,
        score_threshold=score_threshold,
        rewriter=rewriter,  # type: ignore[arg-type]
        reranker=reranker,  # type: ignore[arg-type]
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


def test_document_id_limits_the_text_leg() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[0.0, 1.0, 0.0])
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _save(documents, "ready-2", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="unrelated",
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-2",
        chunk_index=0,
        vector=[0.0, 1.0, 0.0],
        text="the policy applies",
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, _QUESTION, "ready-1")

    assert hits == []
    assert chunk_store.search_calls[0]["document_id"] == "ready-1"
    assert chunk_store.search_calls[0]["ready_ids"] == ["ready-1"]


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


def test_text_hit_on_policy_does_not_require_what() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[0.0, 1.0, 0.0])
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _save(documents, "pending-a", "tenant-a", DocumentStatus.PENDING)
    _save(documents, "ready-b", "tenant-b", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="The Policy applies",
        page=4,
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="pending-a",
        chunk_index=0,
        vector=[0.0, 1.0, 0.0],
        text="the policy applies",
    )
    _point(
        chunk_store,
        tenant_id="tenant-b",
        document_id="ready-b",
        chunk_index=0,
        vector=[0.0, 1.0, 0.0],
        text="the policy applies",
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, _QUESTION)

    assert len(hits) == 1
    assert hits[0].document_id == "ready-1"
    assert hits[0].text == "The Policy applies"
    assert "what" not in hits[0].text
    assert hits[0].score == 1.0
    assert hits[0].page == 4


def test_longer_token_is_not_a_text_match() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[0.0, 1.0, 0.0])
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="policymaking",
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, _QUESTION)

    assert hits == []


def test_text_only_tie_prefers_lower_document_id() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[0.0, 1.0, 0.0])
    _save(documents, "z-doc", "tenant-a", DocumentStatus.READY)
    _save(documents, "a-doc", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="z-doc",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="company policy",
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="a-doc",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="company policy",
    )

    hits = _use_case(documents, embeddings, chunk_store, top_k=1).execute(_ACTOR_A, _QUESTION)

    assert len(hits) == 1
    assert hits[0].document_id == "a-doc"


def test_text_leg_adds_nothing_when_no_distinctive_word_remains() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[0.0, 1.0, 0.0])
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="what this",
    )

    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, "what this")

    assert hits == []


def test_text_match_requires_every_distinctive_word() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[0.0, 1.0, 0.0])
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="the policy",
    )

    missed = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, "policy handbook")
    assert missed == []

    chunk_store.points["ready-1:0"]["text"] = "policy handbook"
    hits = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, "policy handbook")
    assert len(hits) == 1
    assert hits[0].text == "policy handbook"


def test_text_match_uses_a_four_character_cutoff() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[0.0, 1.0, 0.0])
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="policy",
    )

    short_word = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, "cat policy")
    assert len(short_word) == 1

    four_chars = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, "cats policy")
    assert four_chars == []

    chunk_store.points["ready-1:0"]["text"] = "cats policy"
    matched = _use_case(documents, embeddings, chunk_store).execute(_ACTOR_A, "cats policy")
    assert len(matched) == 1


def test_fusion_promotes_a_chunk_found_by_both_legs() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator(vector=[1.0, 0.0, 0.0])
    _save(documents, "a-doc", "tenant-a", DocumentStatus.READY)
    _save(documents, "z-doc", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="a-doc",
        chunk_index=0,
        vector=[0.0, 1.0, 0.0],
        text="company policy",
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="z-doc",
        chunk_index=0,
        vector=[1.0, 0.0, 0.0],
        text="company policy",
    )

    hits = _use_case(documents, embeddings, chunk_store, top_k=1).execute(_ACTOR_A, _QUESTION)

    assert len(hits) == 1
    assert hits[0].document_id == "z-doc"
    assert hits[0].score == 1.0


def test_configured_threshold_drops_a_lower_score() -> None:
    from app.domain.ports.retrieval import RetrievedChunk

    class FixedRetriever:
        def search(self, **kwargs: object) -> list[RetrievedChunk]:
            return [
                RetrievedChunk("low", "low.pdf", 0, 0, "low", 0.24),
                RetrievedChunk("keep", "keep.pdf", 1, 1, "keep", 0.25),
                RetrievedChunk("under-default", "under.pdf", 2, 2, "under", 0.69),
                RetrievedChunk("on-default", "on.pdf", 3, 3, "on", 0.70),
            ]

    documents = InMemoryDocumentRepository()
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    embeddings = FakeEmbeddingGenerator()

    loose = _use_case(
        documents,
        embeddings,
        FixedRetriever(),  # type: ignore[arg-type]
        score_threshold=0.25,
    ).execute(_ACTOR_A, _QUESTION)
    assert [hit.text for hit in loose] == ["keep", "under", "on"]

    strict = _use_case(
        documents,
        embeddings,
        FixedRetriever(),  # type: ignore[arg-type]
        score_threshold=0.70,
    ).execute(_ACTOR_A, _QUESTION)
    assert [hit.text for hit in strict] == ["on"]


class _Rewriter:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.questions: list[str] = []

    def rewrite(self, question: str) -> str:
        self.questions.append(question)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Reranker:
    def __init__(self, result: list | Exception | None = None) -> None:  # noqa: ANN001
        self.result = result
        self.queries: list[str] = []

    def rerank(self, query: str, chunks: list) -> list:  # noqa: ANN001
        self.queries.append(query)
        if isinstance(self.result, Exception):
            raise self.result
        if self.result is None:
            return list(reversed(chunks))
        return self.result


def test_rewrite_failure_searches_the_typed_question() -> None:
    documents = InMemoryDocumentRepository()
    chunk_store = InMemoryChunkStore()
    embeddings = FakeEmbeddingGenerator()
    _save(documents, "ready-1", "tenant-a", DocumentStatus.READY)
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-1",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="policy text",
    )
    rewriter = _Rewriter(RuntimeError("rewrite down"))

    hits = _use_case(documents, embeddings, chunk_store, rewriter=rewriter).execute(
        _ACTOR_A,
        _QUESTION,
    )

    assert len(hits) == 1
    assert embeddings.texts == [[_QUESTION]]
    assert chunk_store.search_calls[0]["question"] == _QUESTION
    assert rewriter.questions == [_QUESTION]


def test_rerank_receives_the_rewritten_query_and_reorders() -> None:
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
        text="alpha",
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-2",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="beta",
    )
    rewriter = _Rewriter("leave policy rules")
    reranker = _Reranker()

    hits = _use_case(
        documents,
        embeddings,
        chunk_store,
        rewriter=rewriter,  # type: ignore[arg-type]
        reranker=reranker,  # type: ignore[arg-type]
    ).execute(_ACTOR_A, _QUESTION)

    assert embeddings.texts == [["leave policy rules"]]
    assert chunk_store.search_calls[0]["question"] == "leave policy rules"
    assert reranker.queries == ["leave policy rules"]
    assert [hit.document_id for hit in hits] == ["ready-2", "ready-1"]


def test_a_different_rerank_set_keeps_fused_order() -> None:
    from app.domain.ports.retrieval import RetrievedChunk

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
        text="alpha",
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-2",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="beta",
    )
    reranker = _Reranker(
        [RetrievedChunk("other", "other.pdf", 0, 0, "other", 1.0)]
    )

    hits = _use_case(
        documents,
        embeddings,
        chunk_store,
        reranker=reranker,  # type: ignore[arg-type]
    ).execute(_ACTOR_A, _QUESTION)

    assert [hit.document_id for hit in hits] == ["ready-1", "ready-2"]


def test_rerank_failure_keeps_fused_order() -> None:
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
        text="alpha",
    )
    _point(
        chunk_store,
        tenant_id="tenant-a",
        document_id="ready-2",
        chunk_index=0,
        vector=[1.0, 1.0, 1.0],
        text="beta",
    )
    reranker = _Reranker(RuntimeError("rerank down"))

    hits = _use_case(
        documents,
        embeddings,
        chunk_store,
        reranker=reranker,  # type: ignore[arg-type]
    ).execute(_ACTOR_A, _QUESTION)

    assert [hit.document_id for hit in hits] == ["ready-1", "ready-2"]


def test_conversation_routes_are_registered() -> None:
    application = create_app(
        settings=Settings(jwt_secret="test-secret-key-at-least-32-bytes!!"),
        readiness_probes=[],
    )
    paths = {getattr(route, "path", "") for route in application.routes}
    assert "/api/v1/conversations" in paths
    assert "/api/v1/conversations/{conversation_id}" in paths
    assert "/api/v1/conversations/{conversation_id}/messages" in paths
    assert all("chat" not in path for path in paths)
