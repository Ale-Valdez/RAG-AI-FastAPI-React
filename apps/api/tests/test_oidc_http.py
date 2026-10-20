from __future__ import annotations

import base64
import http.client
import json
import socket
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from fastapi.testclient import TestClient
from starlette.responses import Response

from app.application.auth.bootstrap_tenant import BootstrapTenant
from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import BootstrapCommand
from app.application.documents.delete_document import DeleteDocument
from app.application.documents.reingest_document import ReingestDocument
from app.application.documents.upload_document import UploadDocument
from app.bootstrap.create_app import create_app
from app.domain.actor import Actor
from app.domain.chat import Conversation
from app.domain.documents import Document
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.auth.oidc import verify_rs256_access_token
from app.infrastructure.config.settings import Settings
from tests.fakes import (
    FakeDocumentJobQueue,
    FakePasswordHasher,
    InMemoryChunkStore,
    InMemoryDocumentBytes,
    InMemoryDocumentRepository,
    InMemoryTenantRepository,
    InMemoryUserRepository,
)

_SECRET = "test-secret-key-at-least-32-bytes!!"
_ISSUER = "https://idp.example/real"
_AUDIENCE = "api://ai-rag"
_JWKS_URL = "https://idp.example/real/jwks"
_USER = "11111111-1111-4111-8111-111111111111"
_TENANT = "22222222-2222-4222-8222-222222222222"
_PDF = b"%PDF-1.4 minimal"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _BuiltApp:
    def __init__(
        self,
        client: TestClient,
        jwt_service: JwtService,
        documents: _RecordingDocuments,
        conversations: _RecordingConversations,
        jobs: FakeDocumentJobQueue,
        users: InMemoryUserRepository,
    ) -> None:
        self.client = client
        self.jwt_service = jwt_service
        self.documents = documents
        self.conversations = conversations
        self.jobs = jobs
        self.users = users


class _RecordingDocuments:
    def __init__(self) -> None:
        self.actors: list[Actor] = []

    def execute(self, actor: Actor) -> list[Document]:
        self.actors.append(actor)
        return []


class _RecordingConversations:
    def __init__(self) -> None:
        self.actors: list[Actor] = []

    def execute(self, actor: Actor) -> list[Conversation]:
        self.actors.append(actor)
        return []


class _KeyVerifier:
    def __init__(
        self,
        public_key: RSAPublicKey,
        *,
        issuer: str = _ISSUER,
        audience: str = _AUDIENCE,
    ) -> None:
        self._public_key = public_key
        self._issuer = issuer
        self._audience = audience

    def verify_access_token(self, token: str) -> dict[str, str]:
        return verify_rs256_access_token(
            token,
            issuer=self._issuer,
            audience=self._audience,
            signing_key=self._public_key,
        )


class _UnusedAsk:
    def execute(
        self,
        actor: Actor,
        question: str,
        document_id: str | None = None,
        conversation_id: str | None = None,
    ) -> Conversation:
        raise AssertionError("ask was not used")


class _UnusedGet:
    def execute(self, actor: Actor, conversation_id: str) -> Conversation:
        raise AssertionError("get was not used")


@pytest.fixture(autouse=True)
def _block_sockets(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    attempts: list[str] = []

    def blocked(*args: object, **kwargs: object) -> None:
        attempts.append("socket")
        raise OSError("socket blocked")

    monkeypatch.setattr(socket, "create_connection", blocked)
    yield
    assert attempts == []


def _settings(**overrides: str) -> Settings:
    values = {
        "jwt_secret": _SECRET,
        "oidc_issuer": "",
        "oidc_audience": "",
        "oidc_jwks_url": "",
    }
    values.update(overrides)
    return Settings(**values)


def _build(
    *,
    users: InMemoryUserRepository | None = None,
    oidc_verifier: _KeyVerifier | None = None,
    settings: Settings | None = None,
) -> _BuiltApp:
    user_repository = users or InMemoryUserRepository()
    hasher = FakePasswordHasher()
    documents = InMemoryDocumentRepository()
    bytes_store = InMemoryDocumentBytes()
    jobs = FakeDocumentJobQueue()
    listed = _RecordingDocuments()
    conversations = _RecordingConversations()
    jwt_service = JwtService(_SECRET)
    client = TestClient(
        create_app(
            settings=settings or _settings(),
            readiness_probes=[],
            login=Login(user_repository, hasher),
            get_current_member=GetCurrentMember(user_repository),
            jwt_service=jwt_service,
            oidc_verifier=oidc_verifier,
            upload_document=UploadDocument(documents, bytes_store, jobs, 1024),
            list_documents=listed,
            delete_document=DeleteDocument(documents, bytes_store, InMemoryChunkStore()),
            reingest_document=ReingestDocument(documents, jobs),
            ask_question=_UnusedAsk(),
            get_conversation=_UnusedGet(),
            list_conversations=conversations,
        )
    )
    return _BuiltApp(client, jwt_service, listed, conversations, jobs, user_repository)


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=5)


def _claims(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "user_id": _USER,
        "tenant_id": _TENANT,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "exp": _future(),
    }
    payload.update(overrides)
    return payload


def _rs256(payload: dict[str, object], private_key: RSAPrivateKey = _PRIVATE_KEY) -> str:
    return jwt.encode(payload, private_key, algorithm="RS256")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _assert_unauthenticated(response: Response) -> None:
    assert response.status_code == 401
    body = response.json()
    assert body["data"] is None
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"].strip()


def _alg_none() -> str:
    def segment(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = {"alg": "none", "typ": "JWT"}
    payload = {"user_id": _USER, "tenant_id": _TENANT, "iss": _ISSUER, "aud": _AUDIENCE}
    return f"{segment(header)}.{segment(payload)}."


def _bootstrap_user() -> InMemoryUserRepository:
    tenants = InMemoryTenantRepository()
    users = InMemoryUserRepository()
    BootstrapTenant(tenants, users, FakePasswordHasher()).execute(
        BootstrapCommand(
            tenant_name="Demo",
            admin_email="admin@example.com",
            admin_password="secret",
        )
    )
    return users


def _patch_jwks_read(monkeypatch: pytest.MonkeyPatch, read: Callable[[], bytes]) -> None:
    class _Response:
        def read(self, *args: object, **kwargs: object) -> bytes:
            return read()

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class _Opener:
        def open(self, request: object, timeout: object = None) -> _Response:
            return _Response()

    monkeypatch.setattr(
        "jwt.jwks_client.urllib.request.build_opener",
        lambda *args: _Opener(),
    )


def test_provider_token_runs_routes_without_a_local_user() -> None:
    app = _build(oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    token = _rs256(_claims())
    headers = _bearer(token)

    listed = app.client.get("/api/v1/documents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["error"] is None
    assert listed.json()["data"] == {"documents": []}
    assert app.documents.actors == [Actor(tenant_id=_TENANT, user_id=_USER)]

    conversations = app.client.get("/api/v1/conversations", headers=headers)
    assert conversations.status_code == 200
    assert conversations.json()["error"] is None
    assert app.conversations.actors == [Actor(tenant_id=_TENANT, user_id=_USER)]

    me = app.client.get("/api/v1/me", headers=headers)
    _assert_unauthenticated(me)


def test_provider_token_without_exp_runs_product_route() -> None:
    app = _build(oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    payload = _claims()
    del payload["exp"]
    response = app.client.get("/api/v1/documents", headers=_bearer(_rs256(payload)))
    assert response.status_code == 200
    assert response.json()["error"] is None
    assert app.documents.actors == [Actor(tenant_id=_TENANT, user_id=_USER)]


def test_me_with_provider_token_returns_stored_user_email() -> None:
    users = _bootstrap_user()
    user = next(iter(users.items.values()))
    app = _build(users=users, oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    token = _rs256(_claims(user_id=user.id.value, tenant_id=user.tenant_id.value))
    response = app.client.get("/api/v1/me", headers=_bearer(token))
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["data"] == {
        "user_id": user.id.value,
        "tenant_id": user.tenant_id.value,
        "email": "admin@example.com",
    }

    missing = app.client.get("/api/v1/me", headers=_bearer(_rs256(_claims())))
    _assert_unauthenticated(missing)


def test_local_hs256_still_works_when_oidc_is_on() -> None:
    users = _bootstrap_user()
    app = _build(users=users, oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    login = app.client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret"},
    )
    assert login.status_code == 200
    assert login.json()["error"] is None
    token = login.json()["data"]["access_token"]
    me = app.client.get("/api/v1/me", headers=_bearer(token))
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "admin@example.com"

    rejected = app.client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong"},
    )
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_oidc_off_rejects_provider_token() -> None:
    app = _build()
    rejected = app.client.get("/api/v1/documents", headers=_bearer(_rs256(_claims())))
    _assert_unauthenticated(rejected)
    token = app.jwt_service.create_access_token(user_id=_USER, tenant_id=_TENANT)
    accepted = app.client.get("/api/v1/documents", headers=_bearer(token))
    assert accepted.status_code == 200
    assert app.documents.actors == [Actor(tenant_id=_TENANT, user_id=_USER)]


def test_missing_bearer_is_unauthenticated() -> None:
    app = _build(oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    _assert_unauthenticated(app.client.get("/api/v1/documents"))


def test_invalid_provider_tokens_are_unauthenticated() -> None:
    app = _build(oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    expired = _claims(exp=datetime.now(UTC) - timedelta(minutes=5))
    sub_only = {
        "sub": _USER,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "exp": _future(),
    }
    tokens = {
        "bad signature": _rs256(_claims(), _OTHER_KEY),
        "wrong issuer": _rs256(_claims(iss="https://other.example")),
        "wrong audience": _rs256(_claims(aud="other-api")),
        "expired": _rs256(expired),
        "null exp": _rs256(_claims(exp=None)),
        "sub only": _rs256(sub_only),
        "blank user": _rs256(_claims(user_id="   ")),
        "blank tenant": _rs256(_claims(tenant_id="")),
        "long user": _rs256(_claims(user_id="u" * 37)),
        "long tenant": _rs256(_claims(tenant_id="t" * 37)),
        "numeric user": _rs256(_claims(user_id=1)),
        "numeric tenant": _rs256(_claims(tenant_id=1)),
        "alg none": _alg_none(),
        "garbage": "not-a-jwt",
    }
    for name, token in tokens.items():
        response = app.client.get("/api/v1/documents", headers=_bearer(token))
        assert response.status_code == 401, name
        body = response.json()
        assert body["data"] is None, name
        assert body["error"]["code"] == "UNAUTHENTICATED", name


def test_jwks_body_failures_are_unauthenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    failures: dict[str, Callable[[], bytes]] = {
        "non-json": lambda: b"not-json",
        "non-utf8": lambda: b"\xff\xfe",
        "truncated": _truncated_jwks_read,
    }
    for name, read in failures.items():
        _patch_jwks_read(monkeypatch, read)
        app = _build(
            settings=_settings(
                oidc_issuer=_ISSUER,
                oidc_audience=_AUDIENCE,
                oidc_jwks_url=_JWKS_URL,
            )
        )
        response = app.client.get("/api/v1/documents", headers=_bearer(_rs256(_claims())))
        assert response.status_code == 401, name
        assert response.json()["error"]["code"] == "UNAUTHENTICATED", name


def _truncated_jwks_read() -> bytes:
    raise http.client.IncompleteRead(b"")


def test_settings_verifier_binds_issuer_audience_and_jwks_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[str] = []

    class _RecordingClient:
        def __init__(self, uri: str, *args: object, **kwargs: object) -> None:
            constructed.append(uri)

        def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
            return SimpleNamespace(key=_PUBLIC_KEY)

    monkeypatch.setattr("app.infrastructure.auth.oidc.PyJWKClient", _RecordingClient)
    app = _build(
        settings=_settings(
            oidc_issuer=_ISSUER,
            oidc_audience=_AUDIENCE,
            oidc_jwks_url=_JWKS_URL,
        )
    )
    assert constructed == [_JWKS_URL]

    accepted = app.client.get("/api/v1/documents", headers=_bearer(_rs256(_claims())))
    assert accepted.status_code == 200
    assert app.documents.actors == [Actor(tenant_id=_TENANT, user_id=_USER)]

    wrong_issuer = app.client.get(
        "/api/v1/documents",
        headers=_bearer(_rs256(_claims(iss="https://other.example"))),
    )
    _assert_unauthenticated(wrong_issuer)
    wrong_audience = app.client.get(
        "/api/v1/documents",
        headers=_bearer(_rs256(_claims(aud="other-api"))),
    )
    _assert_unauthenticated(wrong_audience)
    bad_signature = app.client.get(
        "/api/v1/documents",
        headers=_bearer(_rs256(_claims(), _OTHER_KEY)),
    )
    _assert_unauthenticated(bad_signature)


@pytest.mark.parametrize(
    ("issuer", "audience", "jwks_url"),
    [
        (_ISSUER, "", ""),
        ("", _AUDIENCE, ""),
        ("", "", _JWKS_URL),
        (_ISSUER, _AUDIENCE, ""),
        (_ISSUER, "", _JWKS_URL),
        ("", _AUDIENCE, _JWKS_URL),
    ],
)
def test_partial_oidc_settings_accept_hs256_and_reject_rs256(
    issuer: str,
    audience: str,
    jwks_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[str] = []

    class _BoomClient:
        def __init__(self, uri: str, *args: object, **kwargs: object) -> None:
            constructed.append(uri)
            raise AssertionError("JWKS client built")

    monkeypatch.setattr("app.infrastructure.auth.oidc.PyJWKClient", _BoomClient)
    app = _build(settings=_settings(oidc_issuer=issuer, oidc_audience=audience, oidc_jwks_url=jwks_url))
    assert constructed == []
    token = app.jwt_service.create_access_token(user_id=_USER, tenant_id=_TENANT)
    accepted = app.client.get("/api/v1/documents", headers=_bearer(token))
    assert accepted.status_code == 200
    assert app.documents.actors == [Actor(tenant_id=_TENANT, user_id=_USER)]
    rejected = app.client.get("/api/v1/documents", headers=_bearer(_rs256(_claims())))
    _assert_unauthenticated(rejected)


def test_overlong_hs256_tenant_id_is_unauthenticated() -> None:
    app = _build(oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    accepted = jwt.encode(
        {"user_id": _USER, "tenant_id": _TENANT, "exp": _future()},
        _SECRET,
        algorithm="HS256",
    )
    ok = app.client.get("/api/v1/documents", headers=_bearer(accepted))
    assert ok.status_code == 200

    long_tenant = jwt.encode(
        {"user_id": _USER, "tenant_id": "t" * 37, "exp": _future()},
        _SECRET,
        algorithm="HS256",
    )
    _assert_unauthenticated(app.client.get("/api/v1/documents", headers=_bearer(long_tenant)))

    long_user = jwt.encode(
        {"user_id": "u" * 37, "tenant_id": _TENANT, "exp": _future()},
        _SECRET,
        algorithm="HS256",
    )
    _assert_unauthenticated(app.client.get("/api/v1/documents", headers=_bearer(long_user)))


def test_enqueued_job_has_three_ids_and_no_token() -> None:
    app = _build(oidc_verifier=_KeyVerifier(_PUBLIC_KEY))
    response = app.client.post(
        "/api/v1/documents",
        headers=_bearer(_rs256(_claims())),
        files={"file": ("handbook.pdf", _PDF, "application/pdf")},
    )
    assert response.status_code == 201
    document_id = response.json()["data"]["id"]
    assert app.jobs.jobs == [
        {"tenant_id": _TENANT, "user_id": _USER, "document_id": document_id}
    ]
