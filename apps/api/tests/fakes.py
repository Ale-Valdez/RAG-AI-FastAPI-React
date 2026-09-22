from __future__ import annotations

from app.domain.documents import Document
from app.domain.identity import User, UserId
from app.domain.tenancy import Tenant, TenantId


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self.items: dict[str, Tenant] = {}

    def save(self, tenant: Tenant) -> None:
        self.items[tenant.id.value] = tenant

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        return self.items.get(tenant_id.value)

    def any_exist(self) -> bool:
        return bool(self.items)


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.items: dict[str, User] = {}
        self.by_email: dict[str, User] = {}

    def save(self, user: User) -> None:
        self.items[user.id.value] = user
        self.by_email[user.email] = user

    def get_by_id(self, user_id: UserId) -> User | None:
        return self.items.get(user_id.value)

    def get_by_email(self, email: str) -> User | None:
        return self.by_email.get(email)

    def any_exist(self) -> bool:
        return bool(self.items)


class FakePasswordHasher:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self.items: list[Document] = []
        self.save_calls = 0

    def save(self, document: Document) -> None:
        self.save_calls += 1
        self.items.append(document)

    def list_for_tenant(self, tenant_id: TenantId) -> list[Document]:
        return [item for item in reversed(self.items) if item.tenant_id == tenant_id]


class InMemoryDocumentBytes:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls = 0
        self.delete_calls = 0

    def put(
        self,
        *,
        tenant_id: str,
        document_id: str,
        filename: str,
        content: bytes,
    ) -> None:
        self.put_calls += 1
        self.objects[f"{tenant_id}/{document_id}/{filename}"] = content

    def delete(self, *, tenant_id: str, document_id: str, filename: str) -> None:
        self.delete_calls += 1
        self.objects.pop(f"{tenant_id}/{document_id}/{filename}", None)


class FakeDocumentJobQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.jobs: list[dict[str, str]] = []
        self.fail = fail

    def enqueue(self, *, tenant_id: str, user_id: str, document_id: str) -> None:
        if self.fail:
            raise RuntimeError("enqueue failed")
        self.jobs.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "document_id": document_id,
            }
        )
