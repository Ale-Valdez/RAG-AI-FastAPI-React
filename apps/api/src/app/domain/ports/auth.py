from __future__ import annotations

from typing import Protocol

from app.domain.identity import User, UserId
from app.domain.tenancy import Tenant, TenantId


class TenantRepository(Protocol):
    def save(self, tenant: Tenant) -> None: ...

    def get_by_id(self, tenant_id: TenantId) -> Tenant | None: ...

    def any_exist(self) -> bool: ...


class UserRepository(Protocol):
    def save(self, user: User) -> None: ...

    def get_by_id(self, user_id: UserId) -> User | None: ...

    def get_by_email(self, email: str) -> User | None: ...

    def any_exist(self) -> bool: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...
