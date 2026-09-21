from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapCommand:
    tenant_name: str
    admin_email: str
    admin_password: str


@dataclass(frozen=True)
class BootstrapResult:
    created: bool
    tenant_id: str | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class LoginCommand:
    email: str
    password: str


@dataclass(frozen=True)
class LoginResult:
    user_id: str
    tenant_id: str


@dataclass(frozen=True)
class CurrentMember:
    user_id: str
    tenant_id: str
    email: str
