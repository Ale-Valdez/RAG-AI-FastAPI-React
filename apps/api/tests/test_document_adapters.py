from __future__ import annotations

import pytest

from app.infrastructure.config.settings import Settings
from app.infrastructure.storage.s3_document_bytes import S3DocumentBytes
from app.infrastructure.worker.document_job_queue import CeleryDocumentJobQueue


def test_max_document_size_bytes_converts_mb() -> None:
    assert Settings(max_document_size_mb=20).max_document_size_bytes == 20 * 1024 * 1024


def test_ingestion_settings_defaults() -> None:
    settings = Settings()
    assert settings.max_document_pages == 100
    assert settings.max_concurrent_ingestions_per_tenant == 2
    assert settings.openai_embed_model == "text-embedding-3-small"
    assert settings.rag_top_k == 5
    assert settings.rag_score_threshold == 0.70


def test_s3_document_bytes_put_get_delete_and_path_style(monkeypatch) -> None:  # noqa: ANN001
    put_calls: list[dict[str, object]] = []
    get_calls: list[dict[str, object]] = []
    delete_calls: list[dict[str, object]] = []

    class FakeBody:
        def read(self) -> bytes:
            return b"%PDF-1.4"

    class FakeClient:
        def put_object(self, **kwargs: object) -> None:
            put_calls.append(kwargs)

        def get_object(self, **kwargs: object) -> dict[str, object]:
            get_calls.append(kwargs)
            return {"Body": FakeBody()}

        def delete_object(self, **kwargs: object) -> None:
            delete_calls.append(kwargs)

    store = S3DocumentBytes(
        endpoint_url="http://garage:3900",
        region="garage",
        bucket="ai-rag-documents",
        access_key_id="key",
        secret_access_key="secret",
        use_path_style=True,
        client=FakeClient(),
    )
    store.put(
        tenant_id="t1",
        document_id="d1",
        filename="handbook.pdf",
        content=b"%PDF-1.4",
    )
    assert store.get(tenant_id="t1", document_id="d1", filename="handbook.pdf") == b"%PDF-1.4"
    store.delete(tenant_id="t1", document_id="d1", filename="handbook.pdf")

    assert put_calls == [
        {
            "Bucket": "ai-rag-documents",
            "Key": "t1/d1/handbook.pdf",
            "Body": b"%PDF-1.4",
        }
    ]
    assert get_calls == [
        {"Bucket": "ai-rag-documents", "Key": "t1/d1/handbook.pdf"}
    ]
    assert delete_calls == [
        {"Bucket": "ai-rag-documents", "Key": "t1/d1/handbook.pdf"}
    ]

    captured: dict[str, object] = {}

    def fake_boto_client(service: str, **kwargs: object) -> FakeClient:
        assert service == "s3"
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(
        "app.infrastructure.storage.s3_document_bytes.boto3.client",
        fake_boto_client,
    )
    S3DocumentBytes(
        endpoint_url="http://garage:3900",
        region="garage",
        bucket="ai-rag-documents",
        access_key_id="key",
        secret_access_key="secret",
        use_path_style=True,
    )._get_client()
    config = captured["config"]
    assert config is not None
    assert config.s3.get("addressing_style") == "path"  # type: ignore[union-attr]


def test_celery_document_job_queue_send_task(monkeypatch) -> None:  # noqa: ANN001
    sent: dict[str, object] = {}

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent["name"] = name
        sent["kwargs"] = kwargs.get("kwargs")

    monkeypatch.setattr(
        "app.infrastructure.worker.document_job_queue.celery_app.send_task",
        fake_send_task,
    )
    CeleryDocumentJobQueue().enqueue(
        tenant_id="t1", user_id="u1", document_id="d1"
    )
    assert sent["name"] == "app.infrastructure.worker.tasks.process_document"
    assert sent["kwargs"] == {
        "tenant_id": "t1",
        "user_id": "u1",
        "document_id": "d1",
    }


def test_deferred_task_retries_in_five_seconds(monkeypatch) -> None:  # noqa: ANN001
    from app.application.documents.process_document import ProcessOutcome
    from app.domain.actor import Actor
    from app.infrastructure.worker.tasks import process_document

    class Runner:
        def execute(self, actor: object, document_id: str) -> ProcessOutcome:
            assert isinstance(actor, Actor)
            assert actor.tenant_id == "t1"
            assert actor.user_id == "u1"
            assert document_id == "doc-1"
            return ProcessOutcome.DEFERRED

    monkeypatch.setattr(
        "app.infrastructure.worker.tasks.build_process_document",
        lambda: Runner(),
    )
    countdowns: list[int] = []

    def fake_retry(*_args: object, countdown: int | None = None, **_kwargs: object) -> None:
        if countdown is not None:
            countdowns.append(countdown)
        raise RuntimeError("retry")

    monkeypatch.setattr(process_document, "retry", fake_retry)
    with pytest.raises(RuntimeError, match="retry"):
        process_document.run("t1", "u1", "doc-1")
    assert countdowns == [5]
    assert process_document.max_retries is None


def test_qdrant_upsert_uses_uuid5_cosine_and_payload() -> None:
    from uuid import UUID, uuid5

    from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue

    from app.domain.ports.ingestion import TextChunk
    from app.infrastructure.ingestion.qdrant_chunk_store import QdrantChunkStore

    class FakeClient:
        def __init__(self) -> None:
            self.exists = False
            self.created: tuple[object, object] | None = None
            self.upserts: list[tuple[object, object]] = []
            self.deletes: list[tuple[object, object]] = []

        def collection_exists(self, name: str) -> bool:
            assert name == "chunks"
            return self.exists

        def create_collection(self, *, collection_name: str, vectors_config: object) -> None:
            self.created = (collection_name, vectors_config)
            self.exists = True

        def upsert(self, *, collection_name: str, points: object) -> None:
            self.upserts.append((collection_name, points))

        def delete(self, *, collection_name: str, points_selector: object) -> None:
            self.deletes.append((collection_name, points_selector))

    client = FakeClient()
    store = QdrantChunkStore(client=client)  # type: ignore[arg-type]
    store.upsert_chunks(
        tenant_id="t1",
        document_id="doc-1",
        filename="handbook.pdf",
        chunks=[TextChunk(page=0, chunk_index=0, text="hello")],
        vectors=[[0.1, 0.2]],
    )
    store.delete_by_document(tenant_id="t1", document_id="doc-1")

    assert client.created is not None
    collection_name, vectors = client.created
    assert collection_name == "chunks"
    assert vectors.size == 2  # type: ignore[attr-defined]
    assert vectors.distance is Distance.COSINE  # type: ignore[attr-defined]
    assert client.upserts
    points = client.upserts[0][1]
    point = points[0]  # type: ignore[index]
    assert point.id == str(uuid5(UUID("8b3e1c4a-6f2d-4a7e-9c1b-2d5e6f708192"), "doc-1:0"))
    assert point.payload == {
        "tenant_id": "t1",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 0,
        "text": "hello",
    }
    assert client.deletes[0][0] == "chunks"
    selector = client.deletes[0][1]
    assert isinstance(selector, Filter)
    assert selector.must == [
        FieldCondition(key="tenant_id", match=MatchValue(value="t1")),
        FieldCondition(key="document_id", match=MatchValue(value="doc-1")),
    ]


def test_qdrant_search_filters_tenant_and_does_not_create_collection() -> None:
    from types import SimpleNamespace

    from qdrant_client.http.models import FieldCondition, Filter, MatchAny, MatchValue

    from app.domain.actor import Actor
    from app.infrastructure.ingestion.qdrant_chunk_store import QdrantChunkStore

    class FakeClient:
        def __init__(self) -> None:
            self.exists = True
            self.created: tuple[object, object] | None = None
            self.upserts: list[tuple[object, object]] = []
            self.deletes: list[tuple[object, object]] = []
            self.queries: list[dict[str, object]] = []

        def collection_exists(self, name: str) -> bool:
            assert name == "chunks"
            return self.exists

        def create_collection(self, *, collection_name: str, vectors_config: object) -> None:
            self.created = (collection_name, vectors_config)
            self.exists = True

        def upsert(self, *, collection_name: str, points: object) -> None:
            self.upserts.append((collection_name, points))

        def delete(self, *, collection_name: str, points_selector: object) -> None:
            self.deletes.append((collection_name, points_selector))

        def query_points(self, **kwargs: object) -> SimpleNamespace:
            self.queries.append(kwargs)
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        score=0.91,
                        payload={
                            "tenant_id": "tenant-a",
                            "document_id": "doc-ready",
                            "filename": "handbook.pdf",
                            "page": 2,
                            "chunk_index": 4,
                            "text": "ready text",
                        },
                    )
                ]
            )

    client = FakeClient()
    store = QdrantChunkStore(client=client)  # type: ignore[arg-type]
    actor = Actor(tenant_id="tenant-a", user_id="user-a")
    hits = store.search(
        actor=actor,
        query_vector=[1.0, 0.0, 0.0],
        document_id="doc-ready",
        ready_ids=["doc-ready", "doc-other"],
        top_k=5,
        score_threshold=0.70,
    )
    assert client.created is None
    assert len(client.queries) == 1
    query = client.queries[0]
    assert query["collection_name"] == "chunks"
    assert query["query"] == [1.0, 0.0, 0.0]
    assert query["limit"] == 5
    assert query["score_threshold"] == 0.70
    query_filter = query["query_filter"]
    assert isinstance(query_filter, Filter)
    assert query_filter.must == [
        FieldCondition(key="tenant_id", match=MatchValue(value="tenant-a")),
        FieldCondition(
            key="document_id",
            match=MatchAny(any=["doc-ready", "doc-other"]),
        ),
        FieldCondition(key="document_id", match=MatchValue(value="doc-ready")),
    ]
    assert hits[0].document_id == "doc-ready"
    assert hits[0].filename == "handbook.pdf"
    assert hits[0].page == 2
    assert hits[0].chunk_index == 4
    assert hits[0].text == "ready text"
    assert hits[0].score == 0.91

    corpus_vector = [0.2, 0.4, 0.6]
    corpus = store.search(
        actor=actor,
        query_vector=corpus_vector,
        document_id=None,
        ready_ids=["doc-ready", "doc-other"],
        top_k=5,
        score_threshold=0.70,
    )
    assert corpus[0].text == "ready text"
    assert client.queries[1]["query"] == corpus_vector
    corpus_filter = client.queries[1]["query_filter"]
    assert isinstance(corpus_filter, Filter)
    assert corpus_filter.must == [
        FieldCondition(key="tenant_id", match=MatchValue(value="tenant-a")),
        FieldCondition(
            key="document_id",
            match=MatchAny(any=["doc-ready", "doc-other"]),
        ),
    ]

    queries_before_empty = len(client.queries)
    skipped = store.search(
        actor=actor,
        query_vector=[1.0, 0.0],
        document_id=None,
        ready_ids=[],
        top_k=5,
        score_threshold=0.70,
    )
    assert skipped == []
    assert len(client.queries) == queries_before_empty
    assert client.created is None

    client.exists = False
    client.queries.clear()
    missing = store.search(
        actor=actor,
        query_vector=[1.0, 0.0],
        document_id=None,
        ready_ids=["doc-ready"],
        top_k=5,
        score_threshold=0.70,
    )
    assert missing == []
    assert client.queries == []
    assert client.created is None


def test_openai_embeddings_orders_by_index(monkeypatch) -> None:  # noqa: ANN001
    from types import SimpleNamespace

    from app.infrastructure.ingestion.openai_embeddings import OpenAIEmbeddingGenerator

    class FakeEmbeddingsAPI:
        def create(self, *, model: str, input: list[str]) -> SimpleNamespace:  # noqa: A002
            assert model == "text-embedding-3-small"
            assert input == ["a", "b"]
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[2.0, 2.0]),
                    SimpleNamespace(index=0, embedding=[1.0, 1.0]),
                ]
            )

    class FakeOpenAI:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "key"
            self.embeddings = FakeEmbeddingsAPI()

    monkeypatch.setattr(
        "app.infrastructure.ingestion.openai_embeddings.OpenAI",
        FakeOpenAI,
    )
    vectors = OpenAIEmbeddingGenerator(api_key="key", model="text-embedding-3-small").embed(
        ["a", "b"]
    )
    assert vectors == [[1.0, 1.0], [2.0, 2.0]]


def test_pypdf_extractor_zero_based_pages_including_blank(monkeypatch) -> None:  # noqa: ANN001
    from app.infrastructure.ingestion.pypdf_extractor import PypdfTextExtractor

    class FakePage:
        def __init__(self, text: str | None) -> None:
            self._text = text

        def extract_text(self) -> str | None:
            return self._text

    class FakeReader:
        def __init__(self, _stream: object) -> None:
            self.pages = [FakePage("first"), FakePage(None), FakePage("third")]

    monkeypatch.setattr(
        "app.infrastructure.ingestion.pypdf_extractor.PdfReader",
        FakeReader,
    )
    pages = PypdfTextExtractor().extract_pages(b"%PDF")
    assert [(page.page, page.text) for page in pages] == [
        (0, "first"),
        (1, ""),
        (2, "third"),
    ]


def test_session_bound_commit_while_processing_before_extract(monkeypatch) -> None:  # noqa: ANN001
    from app.application.documents.process_document import ProcessOutcome
    from app.bootstrap.worker import SessionBoundProcessDocument
    from app.domain.actor import Actor
    from app.domain.documents import Document, DocumentStatus
    from app.domain.tenancy import TenantId
    from app.infrastructure.ingestion.page_chunker import PageAwareChunker
    from tests.fakes import (
        FakeEmbeddingGenerator,
        FakePdfTextExtractor,
        InMemoryChunkStore,
        InMemoryDocumentBytes,
        InMemoryDocumentRepository,
    )

    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.PENDING,
        )
    )
    bytes_store.put(
        tenant_id="t1",
        document_id="doc-1",
        filename="handbook.pdf",
        content=b"%PDF",
    )
    commit_statuses: list[DocumentStatus] = []
    extract_after_commit = False

    class FakeSession:
        def commit(self) -> None:
            document = documents.get("doc-1")
            assert document is not None
            commit_statuses.append(document.status)

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    class Repo:
        def __init__(self, _session: object) -> None:
            self._inner = documents

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    monkeypatch.setattr("app.bootstrap.worker.SqlAlchemyDocumentRepository", Repo)

    extractor = FakePdfTextExtractor()
    original_extract = extractor.extract_pages

    def extract_pages(content: bytes):  # noqa: ANN202
        nonlocal extract_after_commit
        assert commit_statuses == [DocumentStatus.PROCESSING]
        extract_after_commit = True
        return original_extract(content)

    extractor.extract_pages = extract_pages  # type: ignore[method-assign]

    outcome = SessionBoundProcessDocument(
        open_session=lambda: FakeSession(),  # type: ignore[arg-type,return-value]
        bytes_store=bytes_store,  # type: ignore[arg-type]
        extractor=extractor,  # type: ignore[arg-type]
        chunker=PageAwareChunker(),
        embeddings=FakeEmbeddingGenerator(),  # type: ignore[arg-type]
        chunk_store=InMemoryChunkStore(),  # type: ignore[arg-type]
        max_pages=100,
        max_concurrent=2,
    ).execute(Actor(tenant_id="t1", user_id="u1"), "doc-1")

    assert outcome is ProcessOutcome.READY
    assert extract_after_commit is True
    assert commit_statuses == [DocumentStatus.PROCESSING, DocumentStatus.READY]


def test_session_bound_commits_failed_status(monkeypatch) -> None:  # noqa: ANN001
    from app.application.documents.process_document import ProcessOutcome
    from app.bootstrap.worker import SessionBoundProcessDocument
    from app.domain.actor import Actor
    from app.domain.documents import Document, DocumentStatus
    from app.domain.tenancy import TenantId
    from app.infrastructure.ingestion.page_chunker import PageAwareChunker
    from tests.fakes import (
        FakeEmbeddingGenerator,
        FakePdfTextExtractor,
        InMemoryChunkStore,
        InMemoryDocumentBytes,
        InMemoryDocumentRepository,
    )

    documents = InMemoryDocumentRepository()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.PENDING,
        )
    )
    bytes_store = InMemoryDocumentBytes()
    bytes_store.put(
        tenant_id="t1",
        document_id="doc-1",
        filename="handbook.pdf",
        content=b"%PDF",
    )
    commit_statuses: list[DocumentStatus] = []

    class FakeSession:
        def commit(self) -> None:
            document = documents.get("doc-1")
            assert document is not None
            commit_statuses.append(document.status)

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    class Repo:
        def __init__(self, _session: object) -> None:
            self._inner = documents

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    monkeypatch.setattr("app.bootstrap.worker.SqlAlchemyDocumentRepository", Repo)

    outcome = SessionBoundProcessDocument(
        open_session=lambda: FakeSession(),  # type: ignore[arg-type,return-value]
        bytes_store=bytes_store,  # type: ignore[arg-type]
        extractor=FakePdfTextExtractor(fail=True),  # type: ignore[arg-type]
        chunker=PageAwareChunker(),
        embeddings=FakeEmbeddingGenerator(),  # type: ignore[arg-type]
        chunk_store=InMemoryChunkStore(),  # type: ignore[arg-type]
        max_pages=100,
        max_concurrent=2,
    ).execute(Actor(tenant_id="t1", user_id="u1"), "doc-1")

    assert outcome is ProcessOutcome.FAILED
    assert commit_statuses == [DocumentStatus.PROCESSING, DocumentStatus.FAILED]
    saved = documents.get("doc-1")
    assert saved is not None
    assert saved.status is DocumentStatus.FAILED
