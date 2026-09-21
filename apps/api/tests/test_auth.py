from app.application.auth.bootstrap_tenant import BootstrapConflictError, BootstrapTenant
from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import BootstrapCommand, LoginCommand
from app.domain.actor import Actor
from app.domain.errors import TenantIsolationError, UnauthenticatedError
from app.domain.identity import User, UserId
from app.domain.tenancy import Tenant, TenantId
from tests.fakes import FakePasswordHasher, InMemoryTenantRepository, InMemoryUserRepository

import pytest


def _bootstrap() -> tuple[BootstrapTenant, InMemoryTenantRepository, InMemoryUserRepository]:
    tenants = InMemoryTenantRepository()
    users = InMemoryUserRepository()
    use_case = BootstrapTenant(tenants, users, FakePasswordHasher())
    return use_case, tenants, users


def test_bootstrap_creates_tenant_and_hashed_user() -> None:
    use_case, tenants, users = _bootstrap()
    result = use_case.execute(
        BootstrapCommand(
            tenant_name="Demo",
            admin_email="admin@example.com",
            admin_password="secret",
        )
    )
    assert result.created is True
    assert len(tenants.items) == 1
    assert len(users.items) == 1
    user = next(iter(users.items.values()))
    assert user.password_hash == "hashed:secret"
    assert user.password_hash != "secret"


def test_bootstrap_idempotent_for_same_email() -> None:
    use_case, tenants, users = _bootstrap()
    command = BootstrapCommand(
        tenant_name="Demo",
        admin_email="admin@example.com",
        admin_password="secret",
    )
    first = use_case.execute(command)
    original_hash = next(iter(users.items.values())).password_hash
    second = use_case.execute(
        BootstrapCommand(
            tenant_name="Other",
            admin_email="admin@example.com",
            admin_password="changed",
        )
    )
    assert first.created is True
    assert second.created is False
    assert len(tenants.items) == 1
    assert len(users.items) == 1
    assert next(iter(users.items.values())).password_hash == original_hash


def test_bootstrap_rejects_new_email_when_store_not_empty() -> None:
    use_case, tenants, users = _bootstrap()
    use_case.execute(
        BootstrapCommand(
            tenant_name="Demo",
            admin_email="admin@example.com",
            admin_password="secret",
        )
    )
    with pytest.raises(BootstrapConflictError):
        use_case.execute(
            BootstrapCommand(
                tenant_name="Other",
                admin_email="other@example.com",
                admin_password="secret",
            )
        )
    assert len(tenants.items) == 1
    assert len(users.items) == 1


def test_bootstrap_rejects_when_only_tenant_exists() -> None:
    use_case, tenants, users = _bootstrap()
    tenants.save(Tenant(id=TenantId("t-existing"), name="Existing"))
    with pytest.raises(BootstrapConflictError):
        use_case.execute(
            BootstrapCommand(
                tenant_name="Demo",
                admin_email="admin@example.com",
                admin_password="secret",
            )
        )
    assert list(tenants.items) == ["t-existing"]
    assert users.items == {}


def test_bootstrap_rejects_when_only_user_exists() -> None:
    use_case, tenants, users = _bootstrap()
    users.save(
        User(
            id=UserId("u-existing"),
            tenant_id=TenantId("t-orphan"),
            email="orphan@example.com",
            password_hash="hashed:x",
        )
    )
    with pytest.raises(BootstrapConflictError):
        use_case.execute(
            BootstrapCommand(
                tenant_name="Demo",
                admin_email="admin@example.com",
                admin_password="secret",
            )
        )
    assert tenants.items == {}
    assert list(users.items) == ["u-existing"]


def test_login_success_and_failure() -> None:
    _, tenants, users = _bootstrap()
    BootstrapTenant(tenants, users, FakePasswordHasher()).execute(
        BootstrapCommand(
            tenant_name="Demo",
            admin_email="admin@example.com",
            admin_password="secret",
        )
    )
    login = Login(users, FakePasswordHasher())
    result = login.execute(LoginCommand(email="admin@example.com", password="secret"))
    assert result.user_id
    assert result.tenant_id

    with pytest.raises(UnauthenticatedError):
        login.execute(LoginCommand(email="admin@example.com", password="wrong"))
    with pytest.raises(UnauthenticatedError):
        login.execute(LoginCommand(email="missing@example.com", password="secret"))


def test_get_current_member_and_isolation() -> None:
    _, tenants, users = _bootstrap()
    result = BootstrapTenant(tenants, users, FakePasswordHasher()).execute(
        BootstrapCommand(
            tenant_name="Demo",
            admin_email="admin@example.com",
            admin_password="secret",
        )
    )
    assert result.user_id is not None
    assert result.tenant_id is not None
    member = GetCurrentMember(users).execute(
        Actor(tenant_id=result.tenant_id, user_id=result.user_id)
    )
    assert member.email == "admin@example.com"
    assert member.tenant_id == result.tenant_id

    with pytest.raises(UnauthenticatedError):
        GetCurrentMember(users).execute(
            Actor(tenant_id=result.tenant_id, user_id="00000000-0000-0000-0000-000000000099")
        )

    with pytest.raises(TenantIsolationError):
        GetCurrentMember(users).execute(
            Actor(tenant_id="00000000-0000-0000-0000-000000000001", user_id=result.user_id)
        )
