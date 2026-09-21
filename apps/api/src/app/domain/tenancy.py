from __future__ import annotations

from dataclasses import dataclass

from app.domain.errors import TenantIsolationError


@dataclass(frozen=True)
class TenantId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("tenant id is required")


@dataclass(frozen=True)
class Tenant:
    id: TenantId
    name: str


def assert_same_tenant(resource_tenant: TenantId, actor_tenant: TenantId) -> None:
    if resource_tenant != actor_tenant:
        raise TenantIsolationError("cross-tenant access is prohibited")
