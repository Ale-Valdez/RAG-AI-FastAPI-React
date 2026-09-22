from __future__ import annotations

from typing import Protocol

from app.domain.documents import Document
from app.domain.tenancy import TenantId


class DocumentRepository(Protocol):
    def save(self, document: Document) -> None: ...

    def get(self, document_id: str) -> Document | None: ...

    def delete(self, document_id: str) -> None: ...

    def list_for_tenant(self, tenant_id: TenantId) -> list[Document]: ...

    def count_processing(self, tenant_id: TenantId) -> int: ...


class DocumentBytes(Protocol):
    def put(
        self,
        *,
        tenant_id: str,
        document_id: str,
        filename: str,
        content: bytes,
    ) -> None: ...

    def get(self, *, tenant_id: str, document_id: str, filename: str) -> bytes: ...

    def delete(self, *, tenant_id: str, document_id: str, filename: str) -> None: ...


class DocumentJobQueue(Protocol):
    def enqueue(self, *, tenant_id: str, user_id: str, document_id: str) -> None: ...
