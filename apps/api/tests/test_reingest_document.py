from __future__ import annotations

import pytest

from app.application.documents.reingest_document import ReingestDocument
from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.errors import InvalidDocumentTransition, NotFoundError
from app.domain.tenancy import TenantId
from tests.fakes import FakeDocumentJobQueue, InMemoryDocumentBytes, InMemoryDocumentRepository


def test_reingest_ready_sets_pending_and_enqueues() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    jobs = FakeDocumentJobQueue()
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
        content=b"%PDF-original",
    )
    document = ReingestDocument(documents, jobs).execute(
        Actor(tenant_id="t1", user_id="u1"),
        "doc-1",
    )
    assert document.id == "doc-1"
    assert document.status is DocumentStatus.PENDING
    assert documents.get("doc-1").status is DocumentStatus.PENDING  # type: ignore[union-attr]
    assert bytes_store.objects["t1/doc-1/handbook.pdf"] == b"%PDF-original"
    assert jobs.jobs == [
        {"tenant_id": "t1", "user_id": "u1", "document_id": "doc-1"}
    ]


def test_reingest_failed_allowed() -> None:
    documents = InMemoryDocumentRepository()
    jobs = FakeDocumentJobQueue()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.FAILED,
        )
    )
    document = ReingestDocument(documents, jobs).execute(
        Actor(tenant_id="t1", user_id="u1"),
        "doc-1",
    )
    assert document.status is DocumentStatus.PENDING


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.PENDING, DocumentStatus.PROCESSING],
)
def test_reingest_wrong_status(status: DocumentStatus) -> None:
    documents = InMemoryDocumentRepository()
    jobs = FakeDocumentJobQueue()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=status,
        )
    )
    with pytest.raises(InvalidDocumentTransition):
        ReingestDocument(documents, jobs).execute(
            Actor(tenant_id="t1", user_id="u1"),
            "doc-1",
        )
    assert jobs.jobs == []
    assert documents.get("doc-1").status is status  # type: ignore[union-attr]


def test_reingest_other_tenant_not_found() -> None:
    documents = InMemoryDocumentRepository()
    jobs = FakeDocumentJobQueue()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t2"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    with pytest.raises(NotFoundError):
        ReingestDocument(documents, jobs).execute(
            Actor(tenant_id="t1", user_id="u1"),
            "doc-1",
        )
    assert jobs.jobs == []
