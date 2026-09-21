from __future__ import annotations

from dataclasses import dataclass

from app.domain.tenancy import TenantId


@dataclass(frozen=True)
class UserId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("user id is required")


@dataclass(frozen=True)
class User:
    id: UserId
    tenant_id: TenantId
    email: str
