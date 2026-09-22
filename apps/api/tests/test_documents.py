from app.domain.documents import Document, DocumentStatus
from app.domain.errors import InvalidDocumentTransition, TenantIsolationError
from app.domain.tenancy import TenantId, assert_same_tenant

import pytest


def test_document_lifecycle() -> None:
    document = Document(id="doc-1", tenant_id=TenantId("t1"), filename="handbook.pdf")
    assert document.status is DocumentStatus.PENDING
    document.mark_processing()
    document.mark_ready()
    assert document.status is DocumentStatus.READY


def test_document_rejects_invalid_transition() -> None:
    document = Document(id="doc-1", tenant_id=TenantId("t1"), filename="handbook.pdf")
    with pytest.raises(InvalidDocumentTransition):
        document.mark_ready()


def test_mark_pending_from_ready_and_failed() -> None:
    ready = Document(
        id="doc-1",
        tenant_id=TenantId("t1"),
        filename="handbook.pdf",
        status=DocumentStatus.READY,
    )
    ready.mark_pending()
    assert ready.status is DocumentStatus.PENDING

    failed = Document(
        id="doc-2",
        tenant_id=TenantId("t1"),
        filename="handbook.pdf",
        status=DocumentStatus.FAILED,
    )
    failed.mark_pending()
    assert failed.status is DocumentStatus.PENDING


def test_mark_pending_rejects_pending_and_processing() -> None:
    pending = Document(id="doc-1", tenant_id=TenantId("t1"), filename="handbook.pdf")
    with pytest.raises(InvalidDocumentTransition):
        pending.mark_pending()

    processing = Document(
        id="doc-2",
        tenant_id=TenantId("t1"),
        filename="handbook.pdf",
        status=DocumentStatus.PROCESSING,
    )
    with pytest.raises(InvalidDocumentTransition):
        processing.mark_pending()


def test_tenant_isolation() -> None:
    with pytest.raises(TenantIsolationError):
        assert_same_tenant(TenantId("t1"), TenantId("t2"))
