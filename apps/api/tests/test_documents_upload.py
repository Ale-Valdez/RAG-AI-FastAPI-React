from __future__ import annotations

import pytest

from app.application.documents.list_documents import ListDocuments
from app.application.documents.models import UploadDocumentCommand
from app.application.documents.upload_document import UploadDocument
from app.domain.actor import Actor
from app.domain.documents import DocumentStatus
from app.domain.errors import InvalidDocument
from app.domain.tenancy import TenantId
from tests.fakes import (
    FakeDocumentJobQueue,
    InMemoryDocumentBytes,
    InMemoryDocumentRepository,
)

_PDF = b"%PDF-1.4 minimal"


def _upload(
    *,
    max_size_bytes: int = 1024,
    jobs: FakeDocumentJobQueue | None = None,
) -> tuple[UploadDocument, InMemoryDocumentRepository, InMemoryDocumentBytes, FakeDocumentJobQueue]:
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    queue = jobs if jobs is not None else FakeDocumentJobQueue()
    use_case = UploadDocument(documents, bytes_store, queue, max_size_bytes)
    return use_case, documents, bytes_store, queue


def test_upload_pdf_creates_pending_stores_bytes_and_enqueues() -> None:
    use_case, documents, bytes_store, queue = _upload()
    actor = Actor(tenant_id="t1", user_id="u1")
    document = use_case.execute(
        actor,
        UploadDocumentCommand(filename="handbook.pdf", content=_PDF),
    )
    assert document.status is DocumentStatus.PENDING
    assert document.filename == "handbook.pdf"
    assert document.tenant_id == TenantId("t1")
    key = f"t1/{document.id}/handbook.pdf"
    assert bytes_store.objects[key] == _PDF
    assert queue.jobs == [
        {"tenant_id": "t1", "user_id": "u1", "document_id": document.id}
    ]
    assert documents.items == [document]


def test_list_documents_for_tenant_newest_first() -> None:
    use_case, documents, _, _ = _upload()
    actor = Actor(tenant_id="t1", user_id="u1")
    first = use_case.execute(actor, UploadDocumentCommand(filename="a.pdf", content=_PDF))
    second = use_case.execute(actor, UploadDocumentCommand(filename="b.pdf", content=_PDF))
    listed = ListDocuments(documents).execute(actor)
    assert [item.id for item in listed] == [second.id, first.id]


def test_duplicate_filenames_allowed() -> None:
    use_case, documents, bytes_store, queue = _upload()
    actor = Actor(tenant_id="t1", user_id="u1")
    first = use_case.execute(
        actor, UploadDocumentCommand(filename="same.pdf", content=_PDF)
    )
    second = use_case.execute(
        actor, UploadDocumentCommand(filename="same.pdf", content=_PDF)
    )
    assert first.id != second.id
    assert set(bytes_store.objects) == {
        f"t1/{first.id}/same.pdf",
        f"t1/{second.id}/same.pdf",
    }
    assert queue.jobs == [
        {"tenant_id": "t1", "user_id": "u1", "document_id": first.id},
        {"tenant_id": "t1", "user_id": "u1", "document_id": second.id},
    ]
    assert documents.items == [first, second]


def test_list_excludes_other_tenant() -> None:
    use_case, documents, bytes_store, _ = _upload()
    use_case.execute(
        Actor(tenant_id="t1", user_id="u1"),
        UploadDocumentCommand(filename="a.pdf", content=_PDF),
    )
    listed = ListDocuments(documents).execute(Actor(tenant_id="t2", user_id="u2"))
    assert listed == []
    assert all(key.startswith("t1/") for key in bytes_store.objects)


@pytest.mark.parametrize(
    ("filename", "content", "max_size"),
    [
        ("ok.pdf", b"NOTPDF", 1024),
        ("ok.pdf", _PDF + b"x" * 100, 50),
        ("", _PDF, 1024),
        ("path/evil.pdf", _PDF, 1024),
        ("path\\evil.pdf", _PDF, 1024),
        ("evil\x00.pdf", _PDF, 1024),
    ],
)
def test_reject_before_put_or_save(filename: str, content: bytes, max_size: int) -> None:
    use_case, documents, bytes_store, queue = _upload(max_size_bytes=max_size)
    with pytest.raises(InvalidDocument):
        use_case.execute(
            Actor(tenant_id="t1", user_id="u1"),
            UploadDocumentCommand(filename=filename, content=content),
        )
    assert bytes_store.put_calls == 0
    assert documents.save_calls == 0
    assert queue.jobs == []


def test_enqueue_failure_deletes_object() -> None:
    use_case, documents, bytes_store, queue = _upload(jobs=FakeDocumentJobQueue(fail=True))
    with pytest.raises(RuntimeError, match="enqueue failed"):
        use_case.execute(
            Actor(tenant_id="t1", user_id="u1"),
            UploadDocumentCommand(filename="handbook.pdf", content=_PDF),
        )
    assert bytes_store.objects == {}
    assert bytes_store.delete_calls == 1
    assert queue.jobs == []
    # Save may have staged a row; the session adapter rolls it back (see persistence test).
    assert documents.save_calls == 1


def test_enqueue_failure_rolls_back_row_in_session() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.infrastructure.persistence.base import Base
    from app.infrastructure.persistence.document_repository import SqlAlchemyDocumentRepository
    from app.infrastructure.persistence.session import session_scope

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    bytes_store = InMemoryDocumentBytes()
    queue = FakeDocumentJobQueue(fail=True)

    with pytest.raises(RuntimeError, match="enqueue failed"):
        with session_scope(factory) as session:
            UploadDocument(
                SqlAlchemyDocumentRepository(session),
                bytes_store,
                queue,
                1024,
            ).execute(
                Actor(tenant_id="t1", user_id="u1"),
                UploadDocumentCommand(filename="handbook.pdf", content=_PDF),
            )

    assert bytes_store.objects == {}
    with factory() as session:
        assert SqlAlchemyDocumentRepository(session).list_for_tenant(TenantId("t1")) == []
