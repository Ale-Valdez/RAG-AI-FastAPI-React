from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.application.auth.bootstrap_tenant import BootstrapTenant
from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import BootstrapCommand
from app.application.documents.delete_document import DeleteDocument
from app.application.documents.list_documents import ListDocuments
from app.application.documents.reingest_document import ReingestDocument
from app.application.documents.upload_document import UploadDocument
from app.bootstrap.create_app import create_app
from app.domain.actor import Actor
from app.domain.documents import Document, DocumentStatus
from app.domain.tenancy import TenantId
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.config.settings import Settings
from tests.fakes import (
    FakeDocumentJobQueue,
    FakePasswordHasher,
    InMemoryChunkStore,
    InMemoryDocumentBytes,
    InMemoryDocumentRepository,
    InMemoryTenantRepository,
    InMemoryUserRepository,
)

_PDF = b"%PDF-1.4 minimal"
_SECRET = "test-secret-key-at-least-32-bytes!!"


def _app() -> tuple[
    TestClient,
    JwtService,
    InMemoryDocumentRepository,
    InMemoryDocumentBytes,
    FakeDocumentJobQueue,
    InMemoryChunkStore,
    str,
    str,
]:
    tenants = InMemoryTenantRepository()
    users = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    BootstrapTenant(tenants, users, hasher).execute(
        BootstrapCommand(
            tenant_name="Demo",
            admin_email="admin@example.com",
            admin_password="secret",
        )
    )
    user = next(iter(users.items.values()))
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    jobs = FakeDocumentJobQueue()
    chunk_store = InMemoryChunkStore()
    jwt_service = JwtService(_SECRET)
    client = TestClient(
        create_app(
            settings=Settings(jwt_secret=_SECRET),
            readiness_probes=[],
            login=Login(users, hasher),
            get_current_member=GetCurrentMember(users),
            jwt_service=jwt_service,
            upload_document=UploadDocument(documents, bytes_store, jobs, 1024),
            list_documents=ListDocuments(documents),
            delete_document=DeleteDocument(documents, bytes_store, chunk_store),
            reingest_document=ReingestDocument(documents, jobs),
        )
    )
    return (
        client,
        jwt_service,
        documents,
        bytes_store,
        jobs,
        chunk_store,
        user.id.value,
        user.tenant_id.value,
    )


def _auth_headers(jwt_service: JwtService, user_id: str, tenant_id: str) -> dict[str, str]:
    token = jwt_service.create_access_token(user_id=user_id, tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}"}


def test_upload_and_list_envelope() -> None:
    client, jwt_service, documents, bytes_store, jobs, _, user_id, tenant_id = _app()
    headers = _auth_headers(jwt_service, user_id, tenant_id)
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["error"] is None
    data = body["data"]
    assert data["filename"] == "handbook.pdf"
    assert data["status"] == "pending"
    assert "created_at" not in data
    document_id = data["id"]
    assert documents.items[0].id == document_id
    assert bytes_store.objects[f"{tenant_id}/{document_id}/handbook.pdf"] == _PDF
    assert jobs.jobs == [
        {"tenant_id": tenant_id, "user_id": user_id, "document_id": document_id}
    ]

    listed = client.get("/api/v1/documents", headers=headers)
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["error"] is None
    assert listed_body["data"]["documents"] == [
        {"id": document_id, "filename": "handbook.pdf", "status": "pending"}
    ]


def test_upload_requires_bearer() -> None:
    client, _, documents, bytes_store, jobs, _, _, _ = _app()
    response = client.post(
        "/api/v1/documents",
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert documents.items == []
    assert bytes_store.objects == {}
    assert jobs.jobs == []


def test_list_requires_bearer() -> None:
    client, _, _, _, _, _, _, _ = _app()
    response = client.get("/api/v1/documents")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_reject_non_pdf_is_domain_rule_violation() -> None:
    client, jwt_service, documents, bytes_store, jobs, _, user_id, tenant_id = _app()
    response = client.post(
        "/api/v1/documents",
        headers=_auth_headers(jwt_service, user_id, tenant_id),
        files={"file": ("handbook.pdf", b"not-a-pdf", "application/pdf")},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOMAIN_RULE_VIOLATION"
    assert documents.items == []
    assert bytes_store.objects == {}
    assert jobs.jobs == []


def test_reject_oversize_is_domain_rule_violation() -> None:
    client, jwt_service, documents, bytes_store, jobs, _, user_id, tenant_id = _app()
    response = client.post(
        "/api/v1/documents",
        headers=_auth_headers(jwt_service, user_id, tenant_id),
        files={"file": ("handbook.pdf", _PDF + b"x" * 2000, "application/pdf")},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOMAIN_RULE_VIOLATION"
    assert documents.items == []
    assert bytes_store.objects == {}
    assert jobs.jobs == []


def test_reject_bad_filename_is_domain_rule_violation() -> None:
    client, jwt_service, documents, bytes_store, jobs, _, user_id, tenant_id = _app()
    response = client.post(
        "/api/v1/documents",
        headers=_auth_headers(jwt_service, user_id, tenant_id),
        files={"file": ("path/evil.pdf", _PDF, "application/pdf")},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOMAIN_RULE_VIOLATION"
    assert documents.items == []
    assert bytes_store.objects == {}
    assert jobs.jobs == []


def test_invalid_bearer_is_unauthenticated() -> None:
    client, _, documents, bytes_store, jobs, _, _, _ = _app()
    response = client.post(
        "/api/v1/documents",
        headers={"Authorization": "Bearer not-a-token"},
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert documents.items == []
    assert bytes_store.objects == {}
    assert jobs.jobs == []


def test_missing_file_is_validation_error() -> None:
    client, jwt_service, documents, bytes_store, jobs, _, user_id, tenant_id = _app()
    response = client.post(
        "/api/v1/documents",
        headers=_auth_headers(jwt_service, user_id, tenant_id),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert documents.items == []
    assert bytes_store.objects == {}
    assert jobs.jobs == []


def test_other_tenant_does_not_see_document() -> None:
    client, jwt_service, documents, bytes_store, _, _, user_id, tenant_id = _app()
    upload = client.post(
        "/api/v1/documents",
        headers=_auth_headers(jwt_service, user_id, tenant_id),
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    assert upload.status_code == 201
    other = client.get(
        "/api/v1/documents",
        headers=_auth_headers(jwt_service, "other-user", "other-tenant"),
    )
    assert other.status_code == 200
    assert other.json()["data"]["documents"] == []
    assert ListDocuments(documents).execute(Actor(tenant_id="other-tenant", user_id="u")) == []
    assert all(key.startswith(f"{tenant_id}/") for key in bytes_store.objects)
    assert TenantId(tenant_id) == documents.items[0].tenant_id


def test_delete_envelope_and_removes_stores() -> None:
    client, jwt_service, documents, bytes_store, _, chunk_store, user_id, tenant_id = _app()
    headers = _auth_headers(jwt_service, user_id, tenant_id)
    upload = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    document_id = upload.json()["data"]["id"]
    chunk_store.points[f"{document_id}:0"] = {
        "tenant_id": tenant_id,
        "document_id": document_id,
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 0,
        "text": "x",
        "vector": [1.0],
    }
    response = client.delete(f"/api/v1/documents/{document_id}", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"data": {"id": document_id}, "error": None}
    assert documents.get(document_id) is None
    assert bytes_store.objects == {}
    assert chunk_store.points == {}


def test_delete_requires_bearer() -> None:
    client, _, documents, bytes_store, _, chunk_store, _, _ = _app()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    response = client.delete("/api/v1/documents/doc-1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert documents.get("doc-1") is not None


def test_delete_other_tenant_is_not_found() -> None:
    client, jwt_service, documents, bytes_store, _, chunk_store, user_id, tenant_id = _app()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("other-tenant"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    bytes_store.put(
        tenant_id="other-tenant",
        document_id="doc-1",
        filename="handbook.pdf",
        content=_PDF,
    )
    chunk_store.points["doc-1:0"] = {
        "tenant_id": "other-tenant",
        "document_id": "doc-1",
        "filename": "handbook.pdf",
        "page": 0,
        "chunk_index": 0,
        "text": "x",
        "vector": [1.0],
    }
    response = client.delete(
        "/api/v1/documents/doc-1",
        headers=_auth_headers(jwt_service, user_id, tenant_id),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert documents.get("doc-1") is not None
    assert bytes_store.objects
    assert chunk_store.points


def test_reingest_envelope() -> None:
    client, jwt_service, documents, bytes_store, jobs, _, user_id, tenant_id = _app()
    headers = _auth_headers(jwt_service, user_id, tenant_id)
    upload = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    document_id = upload.json()["data"]["id"]
    documents.get(document_id).status = DocumentStatus.READY  # type: ignore[union-attr]
    jobs.jobs.clear()
    response = client.post(f"/api/v1/documents/{document_id}/reingest", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"] == {
        "id": document_id,
        "filename": "handbook.pdf",
        "status": "pending",
    }
    assert bytes_store.objects[f"{tenant_id}/{document_id}/handbook.pdf"] == _PDF
    assert jobs.jobs == [
        {"tenant_id": tenant_id, "user_id": user_id, "document_id": document_id}
    ]


def test_reingest_other_tenant_is_not_found() -> None:
    client, jwt_service, documents, _, jobs, _, user_id, tenant_id = _app()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("other-tenant"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    response = client.post(
        "/api/v1/documents/doc-1/reingest",
        headers=_auth_headers(jwt_service, user_id, tenant_id),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert jobs.jobs == []
    assert documents.get("doc-1").status is DocumentStatus.READY  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.PENDING, DocumentStatus.PROCESSING],
)
def test_reingest_wrong_status_is_conflict(status: DocumentStatus) -> None:
    client, jwt_service, documents, bytes_store, jobs, _, user_id, tenant_id = _app()
    headers = _auth_headers(jwt_service, user_id, tenant_id)
    upload = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    document_id = upload.json()["data"]["id"]
    documents.get(document_id).status = status  # type: ignore[union-attr]
    jobs.jobs.clear()
    response = client.post(f"/api/v1/documents/{document_id}/reingest", headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOMAIN_RULE_VIOLATION"
    assert jobs.jobs == []


def test_delete_and_reingest_reject_invalid_bearer() -> None:
    client, _, documents, bytes_store, jobs, chunk_store, _, _ = _app()
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
        content=_PDF,
    )
    headers = {"Authorization": "Bearer not-a-token"}
    deleted = client.delete("/api/v1/documents/doc-1", headers=headers)
    reingested = client.post("/api/v1/documents/doc-1/reingest", headers=headers)
    assert deleted.status_code == 401
    assert reingested.status_code == 401
    assert deleted.json()["error"]["code"] == "UNAUTHENTICATED"
    assert reingested.json()["error"]["code"] == "UNAUTHENTICATED"
    assert documents.get("doc-1") is not None
    assert bytes_store.objects
    assert jobs.jobs == []
    assert chunk_store.points == {}


def test_reingest_requires_bearer() -> None:
    client, _, documents, _, jobs, _, _, _ = _app()
    documents.save(
        Document(
            id="doc-1",
            tenant_id=TenantId("t1"),
            filename="handbook.pdf",
            status=DocumentStatus.READY,
        )
    )
    response = client.post("/api/v1/documents/doc-1/reingest")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert jobs.jobs == []
