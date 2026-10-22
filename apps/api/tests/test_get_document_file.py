from __future__ import annotations

import pytest

from app.application.documents.get_document_file import GetDocumentFile
from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.errors import NotFoundError
from app.domain.tenancy import TenantId
from tests.fakes import InMemoryDocumentBytes, InMemoryDocumentRepository

_PDF = b"%PDF-1.4"


def test_owned_file_returns_filename_and_bytes() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.FAILED,
        )
    )
    bytes_store.put(
        tenant_id="t1",
        document_id="doc-1",
        filename="handbook.pdf",
        content=_PDF,
    )
    loaded = GetDocumentFile(documents, bytes_store).execute(
        Actor(tenant_id="t1", user_id="u1"),
        "doc-1",
    )
    assert loaded.filename == "handbook.pdf"
    assert loaded.content == _PDF


@pytest.mark.parametrize(
    "status",
    [
        DocumentStatus.PENDING,
        DocumentStatus.PROCESSING,
        DocumentStatus.READY,
        DocumentStatus.FAILED,
    ],
)
def test_owned_file_any_status(status: DocumentStatus) -> None:
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
    bytes_store.put(
        tenant_id="t1",
        document_id="doc-1",
        filename="handbook.pdf",
        content=_PDF,
    )
    loaded = GetDocumentFile(documents, bytes_store).execute(
        Actor(tenant_id="t1", user_id="u1"),
        "doc-1",
    )
    assert loaded.content == _PDF


def test_missing_document_is_not_found() -> None:
    with pytest.raises(NotFoundError, match="document not found"):
        GetDocumentFile(InMemoryDocumentRepository(), InMemoryDocumentBytes()).execute(
            Actor(tenant_id="t1", user_id="u1"),
            "missing",
        )


def test_other_tenant_is_not_found() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
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
        content=_PDF,
    )
    with pytest.raises(NotFoundError, match="document not found"):
        GetDocumentFile(documents, bytes_store).execute(
            Actor(tenant_id="t1", user_id="u1"),
            "doc-1",
        )
    assert bytes_store.get_calls == 0
    assert bytes_store.objects


def test_missing_object_is_not_found() -> None:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    with pytest.raises(NotFoundError, match="document not found"):
        GetDocumentFile(documents, bytes_store).execute(
            Actor(tenant_id="t1", user_id="u1"),
            "doc-1",
        )
    assert bytes_store.get_calls == 1
