from __future__ import annotations

import uuid

from app.application.auth.models import BootstrapCommand, BootstrapResult
from app.domain.errors import DomainError
from app.domain.identity import User, UserId
from app.domain.ports.auth import PasswordHasher, TenantRepository, UserRepository
from app.domain.tenancy import Tenant, TenantId


class BootstrapConflictError(DomainError):
    """Bootstrap refused because a different tenant or user already exists."""


class BootstrapTenant:
    def __init__(
        self,
        tenants: TenantRepository,
        users: UserRepository,
        password_hasher: PasswordHasher,
    ) -> None:
        self._tenants = tenants
        self._users = users
        self._password_hasher = password_hasher

    def execute(self, command: BootstrapCommand) -> BootstrapResult:
        existing = self._users.get_by_email(command.admin_email)
        if existing is not None:
            return BootstrapResult(created=False)

        if self._tenants.any_exist() or self._users.any_exist():
            raise BootstrapConflictError(
                "bootstrap refused: a tenant or user already exists"
            )

        tenant_id = TenantId(str(uuid.uuid4()))
        user_id = UserId(str(uuid.uuid4()))
        tenant = Tenant(id=tenant_id, name=command.tenant_name)
        user = User(
            id=user_id,
            tenant_id=tenant_id,
            email=command.admin_email,
            password_hash=self._password_hasher.hash(command.admin_password),
        )
        self._tenants.save(tenant)
        self._users.save(user)
        return BootstrapResult(
            created=True,
            tenant_id=tenant_id.value,
            user_id=user_id.value,
        )
