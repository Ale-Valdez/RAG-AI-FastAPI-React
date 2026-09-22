from __future__ import annotations

import pytest

from app.application.documents.delete_document import DeleteDocument
from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.errors import NotFoundError
from app.domain.tenancy import TenantId
from tests.fakes import InMemoryChunkStore, InMemoryDocumentBytes, InMemoryDocumentRepository


def test_delete_removes_points_bytes_and_row() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    chunk_store = InMemoryChunkStore()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    bytes_store.put(
        tenant_id="t1",
        document_id="doc-1",
        filename="handbook.pdf",
        content=b"%PDF-1.4",
    )
    chunk_store.points["doc-1:0"] = {
        "tenant_id": "t1",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 0,
        "text": "hello",
        "vector": [1.0],
    }
    deleted = DeleteDocument(documents, bytes_store, chunk_store).execute(
        Actor(tenant_id="t1", user_id="u1"),
        "doc-1",
    )
    assert deleted == "doc-1"
    assert documents.get("doc-1") is None
    assert bytes_store.objects == {}
    assert chunk_store.points == {}
    assert chunk_store.delete_calls == [("t1", "doc-1")]


@pytest.mark.parametrize(
    "status",
    [
        DocumentStatus.PENDING,
        DocumentStatus.PROCESSING,
        DocumentStatus.READY,
        DocumentStatus.FAILED,
    ],
)
def test_delete_any_status(status: DocumentStatus) -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    chunk_store = InMemoryChunkStore()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=status,
        )
    )
    bytes_store.put(
        tenant_id="t1",
        document_id="doc-1",
        filename="handbook.pdf",
        content=b"%PDF",
    )
    DeleteDocument(documents, bytes_store, chunk_store).execute(
        Actor(tenant_id="t1", user_id="u1"),
        "doc-1",
    )
    assert documents.items == []


def test_delete_other_tenant_is_not_found() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    chunk_store = InMemoryChunkStore()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t2"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    bytes_store.put(
        tenant_id="t2",
        document_id="doc-1",
        filename="handbook.pdf",
        content=b"%PDF",
    )
    chunk_store.points["doc-1:0"] = {
        "tenant_id": "t2",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 0,
        "text": "hello",
        "vector": [1.0],
    }
    with pytest.raises(NotFoundError):
        DeleteDocument(documents, bytes_store, chunk_store).execute(
            Actor(tenant_id="t1", user_id="u1"),
            "doc-1",
        )
    assert documents.get("doc-1") is not None
    assert bytes_store.objects
    assert chunk_store.points
    assert chunk_store.delete_calls == []
