from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.application.auth.bootstrap_tenant import BootstrapTenant
from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import BootstrapCommand, CurrentMember
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.session import create_db_engine, create_session_factory
from app.infrastructure.persistence.tenant_repository import SqlAlchemyTenantRepository
from app.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.bootstrap.create_app import create_app
from app.domain.actor import Actor
from app.domain.errors import DomainError, NotFoundError, TenantIsolationError
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.config.settings import Settings
from tests.fakes import FakePasswordHasher, InMemoryTenantRepository, InMemoryUserRepository


def _app_with_user(
    *,
    email: str = "admin@example.com",
    password: str = "secret",
) -> tuple[TestClient, JwtService, str, str]:
    tenants = InMemoryTenantRepository()
    users = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    BootstrapTenant(tenants, users, hasher).execute(
        BootstrapCommand(tenant_name="Demo", admin_email=email, admin_password=password)
    )
    user = next(iter(users.items.values()))
    jwt_service = JwtService("test-secret-key-at-least-32-bytes!!")
    client = TestClient(
        create_app(
            settings=Settings(jwt_secret="test-secret-key-at-least-32-bytes!!"),
            readiness_probes=[],
            login=Login(users, hasher),
            get_current_member=GetCurrentMember(users),
            jwt_service=jwt_service,
        )
    )
    return client, jwt_service, user.id.value, user.tenant_id.value


def test_login_success_returns_envelope_with_jwt() -> None:
    client, jwt_service, user_id, tenant_id = _app_with_user()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    token = body["data"]["access_token"]
    claims = jwt_service.verify_access_token(token)
    assert claims["user_id"] == user_id
    assert claims["tenant_id"] == tenant_id
    decoded = jwt.decode(token, "test-secret-key-at-least-32-bytes!!", algorithms=["HS256"])
    exp = datetime.fromtimestamp(decoded["exp"], tz=UTC)
    iat = datetime.fromtimestamp(decoded["iat"], tz=UTC)
    assert timedelta(days=14, hours=23) < (exp - iat) <= timedelta(days=15)


def test_login_failure_is_invalid_credentials() -> None:
    client, _, _, _ = _app_with_user()
    for payload in (
        {"email": "admin@example.com", "password": "wrong"},
        {"email": "missing@example.com", "password": "secret"},
    ):
        response = client.post("/api/v1/auth/login", json=payload)
        assert response.status_code == 401
        body = response.json()
        assert body["data"] is None
        assert body["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_bearer_and_returns_member() -> None:
    client, jwt_service, user_id, tenant_id = _app_with_user()
    missing = client.get("/api/v1/me")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "UNAUTHENTICATED"

    bad = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "UNAUTHENTICATED"

    token = jwt_service.create_access_token(user_id=user_id, tenant_id=tenant_id)
    ok = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data == {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "email": "admin@example.com",
    }


def test_expired_token_is_unauthenticated() -> None:
    client, _, user_id, tenant_id = _app_with_user()
    expired = jwt.encode(
        {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        "test-secret-key-at-least-32-bytes!!",
        algorithm="HS256",
    )
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_verified_token_for_missing_user_is_unauthenticated() -> None:
    client, jwt_service, _, tenant_id = _app_with_user()
    token = jwt_service.create_access_token(
        user_id="00000000-0000-0000-0000-000000000099",
        tenant_id=tenant_id,
    )
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_domain_error_status_map_on_product_routes() -> None:
    class RaisingMember:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        def execute(self, actor: Actor) -> CurrentMember:
            raise self._exc

    jwt_service = JwtService("test-secret-key-at-least-32-bytes!!")
    token = jwt_service.create_access_token(user_id="u1", tenant_id="t1")
    headers = {"Authorization": f"Bearer {token}"}

    cases = [
        (TenantIsolationError("nope"), 403, "TENANT_ISOLATION"),
        (NotFoundError("gone"), 404, "NOT_FOUND"),
        (DomainError("rule"), 409, "DOMAIN_RULE_VIOLATION"),
    ]
    for exc, status, code in cases:
        client = TestClient(
            create_app(
                settings=Settings(jwt_secret="test-secret-key-at-least-32-bytes!!"),
                readiness_probes=[],
                login=Login(InMemoryUserRepository(), FakePasswordHasher()),
                get_current_member=RaisingMember(exc),
                jwt_service=jwt_service,
            )
        )
        response = client.get("/api/v1/me", headers=headers)
        assert response.status_code == status
        body = response.json()
        assert body["data"] is None
        assert body["error"]["code"] == code


def test_health_stays_outside_envelope() -> None:
    client, _, _, _ = _app_with_user()
    health = client.get("/api/health")
    assert health.status_code == 200
    assert "error" not in health.json()
    assert health.json()["status"] == "ok"


def test_token_with_bad_claim_shape_is_unauthenticated() -> None:
    client, _, _, _ = _app_with_user()
    secret = "test-secret-key-at-least-32-bytes!!"
    exp = datetime.now(UTC) + timedelta(minutes=5)
    payloads = (
        {"exp": exp},
        {"user_id": "", "tenant_id": "t1", "exp": exp},
        {"user_id": "u1", "tenant_id": "   ", "exp": exp},
        {"user_id": 1, "tenant_id": "t1", "exp": exp},
    )
    for payload in payloads:
        token = jwt.encode(payload, secret, algorithm="HS256")
        response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_framework_and_unhandled_product_errors_use_envelope() -> None:
    client, _, _, _ = _app_with_user()
    missing = client.get("/api/v1/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert "detail" not in missing.json()

    wrong_method = client.get("/api/v1/auth/login")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "detail" not in wrong_method.json()

    outside = client.get("/api/does-not-exist")
    assert outside.status_code == 404
    assert "detail" in outside.json()

    class Boom:
        def execute(self, command: object) -> object:
            raise RuntimeError("db down")

    secret = "test-secret-key-at-least-32-bytes!!"
    crashing = TestClient(
        create_app(
            settings=Settings(jwt_secret=secret),
            readiness_probes=[],
            login=Boom(),
            get_current_member=GetCurrentMember(InMemoryUserRepository()),
            jwt_service=JwtService(secret),
        ),
        raise_server_exceptions=False,
    )
    failed = crashing.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret"},
    )
    assert failed.status_code == 500
    body = failed.json()
    assert body["data"] is None
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "db down" not in failed.text


def test_default_session_login_and_me(tmp_path) -> None:  # noqa: ANN001
    database_url = f"sqlite:///{tmp_path / 'app.sqlite'}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    hasher = Argon2PasswordHasher()
    with factory() as session:
        BootstrapTenant(
            SqlAlchemyTenantRepository(session),
            SqlAlchemyUserRepository(session),
            hasher,
        ).execute(
            BootstrapCommand(
                tenant_name="Demo",
                admin_email="admin@example.com",
                admin_password="secret-secret",
            )
        )
        session.commit()

    secret = "test-secret-key-at-least-32-bytes!!"
    client = TestClient(
        create_app(
            settings=Settings(database_url=database_url, jwt_secret=secret),
            readiness_probes=[],
        )
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret-secret"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "admin@example.com"


def test_create_app_refuses_placeholder_jwt_secret() -> None:
    for secret in ("change-me", "", "   "):
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            create_app(settings=Settings(jwt_secret=secret), readiness_probes=[])


def test_product_validation_error_uses_envelope() -> None:
    client, _, _, _ = _app_with_user()
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "detail" not in body
