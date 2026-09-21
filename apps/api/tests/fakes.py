from __future__ import annotations

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
