from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.cli import main
from app.domain.tenancy import TenantId
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from tests.fakes import InMemoryTenantRepository, InMemoryUserRepository


class _TenantRepo:
    def __init__(self, _session: object, tenants: InMemoryTenantRepository) -> None:
        self._tenants = tenants

    def save(self, tenant):  # noqa: ANN001
        self._tenants.save(tenant)

    def get_by_id(self, tenant_id: TenantId):
        return self._tenants.get_by_id(tenant_id)

    def any_exist(self) -> bool:
        return self._tenants.any_exist()


class _UserRepo:
    def __init__(self, _session: object, users: InMemoryUserRepository) -> None:
        self._users = users

    def save(self, user):  # noqa: ANN001
        self._users.save(user)

    def get_by_id(self, user_id):  # noqa: ANN001
        return self._users.get_by_id(user_id)

    def get_by_email(self, email: str):
        return self._users.get_by_email(email)

    def any_exist(self) -> bool:
        return self._users.any_exist()


def _patch_store(monkeypatch: pytest.MonkeyPatch) -> tuple[InMemoryTenantRepository, InMemoryUserRepository]:
    tenants = InMemoryTenantRepository()
    users = InMemoryUserRepository()

    @contextmanager
    def _scope(_factory):  # noqa: ANN001
        yield None

    monkeypatch.setattr("app.cli.LazySessionFactory", lambda _url: object())
    monkeypatch.setattr("app.cli.session_scope", _scope)
    monkeypatch.setattr(
        "app.cli.SqlAlchemyTenantRepository",
        lambda session: _TenantRepo(session, tenants),
    )
    monkeypatch.setattr(
        "app.cli.SqlAlchemyUserRepository",
        lambda session: _UserRepo(session, users),
    )
    return tenants, users


def _set_bootstrap_env(monkeypatch: pytest.MonkeyPatch, *, name: str, email: str, password: str) -> None:
    monkeypatch.setenv("BOOTSTRAP_TENANT_NAME", name)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", email)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", password)


def test_bootstrap_cli_missing_env_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_bootstrap_env(monkeypatch, name="", email="", password="")
    with pytest.raises(SystemExit) as caught:
        main(["bootstrap"])
    assert caught.value.code == 1


def test_bootstrap_cli_creates_then_ignores_same_email(monkeypatch: pytest.MonkeyPatch) -> None:
    tenants, users = _patch_store(monkeypatch)
    _set_bootstrap_env(
        monkeypatch,
        name="Demo Company",
        email="admin@example.com",
        password="secret-secret",
    )
    assert main(["bootstrap"]) == 0
    assert len(tenants.items) == 1
    assert len(users.items) == 1
    stored_hash = next(iter(users.items.values())).password_hash
    assert stored_hash != "secret-secret"
    assert stored_hash.startswith("$argon2")

    _set_bootstrap_env(
        monkeypatch,
        name="Other",
        email="admin@example.com",
        password="different-secret",
    )
    assert main(["bootstrap"]) == 0
    assert len(tenants.items) == 1
    assert len(users.items) == 1
    assert next(iter(users.items.values())).password_hash == stored_hash


def test_bootstrap_cli_strips_password(monkeypatch: pytest.MonkeyPatch) -> None:
    _tenants, users = _patch_store(monkeypatch)
    _set_bootstrap_env(
        monkeypatch,
        name="Demo Company",
        email="admin@example.com",
        password="secret-secret  ",
    )
    assert main(["bootstrap"]) == 0
    stored_hash = next(iter(users.items.values())).password_hash
    hasher = Argon2PasswordHasher()
    assert hasher.verify("secret-secret", stored_hash) is True
    assert hasher.verify("secret-secret  ", stored_hash) is False


def test_bootstrap_cli_refuses_new_email(monkeypatch: pytest.MonkeyPatch) -> None:
    tenants, users = _patch_store(monkeypatch)
    _set_bootstrap_env(
        monkeypatch,
        name="Demo Company",
        email="admin@example.com",
        password="secret-secret",
    )
    assert main(["bootstrap"]) == 0
    _set_bootstrap_env(
        monkeypatch,
        name="Other",
        email="other@example.com",
        password="secret-secret",
    )
    assert main(["bootstrap"]) == 1
    assert len(tenants.items) == 1
    assert len(users.items) == 1
    assert "other@example.com" not in users.by_email
