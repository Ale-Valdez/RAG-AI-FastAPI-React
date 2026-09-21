from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    """Authenticated caller; tenant_id is the isolation key for tenant use cases."""

    tenant_id: str
    user_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not self.user_id.strip():
            raise ValueError("user_id is required")
