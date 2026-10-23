from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.application.auth.bootstrap_tenant import BootstrapTenant
from app.application.auth.get_current_member import GetCurrentMember
from app.application.auth.login import Login
from app.application.auth.models import BootstrapCommand
from app.application.documents.process_document import ProcessOutcome
from app.application.documents.upload_document import UploadDocument
from app.bootstrap.create_app import create_app
from app.domain.errors import NotFoundError
from app.infrastructure.auth.jwt import JwtService
from app.infrastructure.config.settings import Settings
from app.infrastructure.ops_log import CORRELATION_HEADER
from app.infrastructure.worker.celery_app import celery_app
from app.infrastructure.worker.document_job_queue import CeleryDocumentJobQueue
from app.infrastructure.worker.tasks import process_document
from tests.fakes import (
    FakePasswordHasher,
    InMemoryDocumentBytes,
    InMemoryDocumentRepository,
    InMemoryTenantRepository,
    InMemoryUserRepository,
)

_SECRET = "test-secret-key-at-least-32-bytes!!"
_EMAIL = "ada@example.com"
_PASSWORD = "password-must-not-be-logged"
_HTTP_KEYS = {"event", "correlation_id", "tenant_id", "route", "status_code"}
_JOB_KEYS = {"event", "correlation_id", "tenant_id", "document_id", "status"}


def _ops(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != "app.ops":
            continue
        assert record.levelno == logging.INFO
        assert record.exc_info is None
        payload = json.loads(record.getMessage())
        assert isinstance(payload, dict)
        found.append(payload)
    return found


@pytest.fixture
def capops(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="app.ops")
    return caplog


def _member_app(**overrides: object) -> tuple[TestClient, JwtService, str, str]:
    tenants = InMemoryTenantRepository()
    users = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    BootstrapTenant(tenants, users, hasher).execute(
        BootstrapCommand(tenant_name="Demo", admin_email=_EMAIL, admin_password=_PASSWORD)
    )
    user = next(iter(users.items.values()))
    jwt_service = JwtService(_SECRET)
    client = TestClient(
        create_app(
            settings=Settings(jwt_secret=_SECRET),
            readiness_probes=[],
            login=Login(users, hasher),
            get_current_member=GetCurrentMember(users),
            jwt_service=jwt_service,
            **overrides,  # type: ignore[arg-type]
        )
    )
    return client, jwt_service, user.id.value, user.tenant_id.value


def _auth(jwt_service: JwtService, user_id: str, tenant_id: str) -> tuple[dict[str, str], str]:
    token = jwt_service.create_access_token(user_id=user_id, tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}"}, token


@contextmanager
def _pushed(headers: dict[str, str] | None) -> Iterator[None]:
    if headers is None:
        process_document.push_request()
    else:
        process_document.push_request(headers=headers)
    try:
        yield
    finally:
        process_document.pop_request()


class _Outcome:
    def __init__(self, outcome: ProcessOutcome) -> None:
        self.outcome = outcome

    def execute(self, actor: object, document_id: str) -> ProcessOutcome:
        return self.outcome


class _Boom:
    def execute(self, actor: object, document_id: str) -> ProcessOutcome:
        raise RuntimeError("secret-exception-text-must-not-be-logged")


class _LoginBoom:
    def execute(self, command: object) -> object:
        raise RuntimeError("secret-exception-text-must-not-be-logged")


class _MissingDocument:
    def execute(self, actor: object, document_id: str) -> str:
        raise NotFoundError("document not found")


def test_authenticated_request_logs_tenant_route_and_uuid(
    capops: pytest.LogCaptureFixture,
) -> None:
    client, jwt_service, user_id, tenant_id = _member_app()
    headers, token = _auth(jwt_service, user_id, tenant_id)
    headers[CORRELATION_HEADER] = "client-supplied-id"
    response = client.get("/api/v1/me?access_token=query-secret", headers=headers)

    assert response.status_code == 200
    assert response.json()["error"] is None
    assert CORRELATION_HEADER not in {name.lower() for name in response.headers}
    logs = _ops(capops)
    assert len(logs) == 1
    record = logs[0]
    assert set(record) == _HTTP_KEYS
    assert record["event"] == "http.request"
    assert record["tenant_id"] == tenant_id
    assert record["route"] == "GET /api/v1/me"
    assert record["status_code"] == 200
    correlation_id = record["correlation_id"]
    assert isinstance(correlation_id, str)
    UUID(correlation_id)
    assert correlation_id != "client-supplied-id"
    message = capops.records[-1].getMessage()
    assert token not in message
    assert _SECRET not in message
    assert "query-secret" not in message
    assert "client-supplied-id" not in message
    assert user_id not in message


def test_login_logs_status_without_password_or_token(capops: pytest.LogCaptureFixture) -> None:
    client, _, _, _ = _member_app()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )

    assert response.status_code == 200
    token = response.json()["data"]["access_token"]
    logs = _ops(capops)
    assert len(logs) == 1
    record = logs[0]
    assert set(record) == _HTTP_KEYS
    assert record == {
        "event": "http.request",
        "correlation_id": record["correlation_id"],
        "tenant_id": None,
        "route": "POST /api/v1/auth/login",
        "status_code": 200,
    }
    message = capops.text
    assert _PASSWORD not in message
    assert _SECRET not in message
    assert token not in message
    assert _EMAIL not in message


def test_bad_token_logs_401_without_the_token(capops: pytest.LogCaptureFixture) -> None:
    client, _, _, _ = _member_app()
    bad_token = "this-token-must-not-be-logged"
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {bad_token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    logs = _ops(capops)
    assert len(logs) == 1
    record = logs[0]
    assert record["event"] == "http.request"
    assert record["tenant_id"] is None
    assert record["route"] == "GET /api/v1/me"
    assert record["status_code"] == 401
    assert bad_token not in capops.text
    assert "Authorization" not in capops.text


def test_missing_route_logs_404(capops: pytest.LogCaptureFixture) -> None:
    client, _, _, _ = _member_app()
    response = client.get("/api/v1/does-not-exist?q=hidden")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    logs = _ops(capops)
    assert len(logs) == 1
    assert logs[0]["tenant_id"] is None
    assert logs[0]["route"] == "GET /api/v1/does-not-exist"
    assert logs[0]["status_code"] == 404
    assert "hidden" not in capops.text


def test_unhandled_product_error_logs_500_without_exception_text(
    capops: pytest.LogCaptureFixture,
) -> None:
    client = TestClient(
        create_app(
            settings=Settings(jwt_secret=_SECRET),
            readiness_probes=[],
            login=_LoginBoom(),
            get_current_member=GetCurrentMember(InMemoryUserRepository()),
            jwt_service=JwtService(_SECRET),
        ),
        raise_server_exceptions=False,
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-exception-text-must-not-be-logged" not in response.text
    logs = _ops(capops)
    assert len(logs) == 1
    assert logs[0]["tenant_id"] is None
    assert logs[0]["route"] == "POST /api/v1/auth/login"
    assert logs[0]["status_code"] == 500
    assert "secret-exception-text-must-not-be-logged" not in capops.text
    assert "Traceback" not in capops.text


def test_probes_are_not_ops_logs(capops: pytest.LogCaptureFixture) -> None:
    client, _, _, _ = _member_app()
    health = client.get("/api/health")
    ready = client.get("/api/ready")

    assert health.status_code == 200
    assert ready.status_code == 200
    assert "error" not in health.json()
    assert "data" not in health.json()
    assert "error" not in ready.json()
    assert "data" not in ready.json()
    assert health.json()["status"] == "ok"
    assert ready.json()["status"] == "ok"
    assert _ops(capops) == []


def test_matched_template_omits_the_path_value(capops: pytest.LogCaptureFixture) -> None:
    client, jwt_service, user_id, tenant_id = _member_app(delete_document=_MissingDocument())
    headers, _token = _auth(jwt_service, user_id, tenant_id)
    response = client.delete("/api/v1/documents/doc-123", headers=headers)

    assert response.status_code == 404
    logs = _ops(capops)
    assert len(logs) == 1
    assert logs[0]["route"] == "DELETE /api/v1/documents/{document_id}"
    assert logs[0]["tenant_id"] == tenant_id
    assert logs[0]["status_code"] == 404
    assert "doc-123" not in capops.text


def test_upload_enqueue_header_matches_request_id(
    monkeypatch: pytest.MonkeyPatch,
    capops: pytest.LogCaptureFixture,
) -> None:
    sent: dict[str, object] = {}

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent["name"] = name
        sent["kwargs"] = kwargs.get("kwargs")
        sent["headers"] = kwargs.get("headers")

    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    documents = InMemoryDocumentRepository()
    client, jwt_service, user_id, tenant_id = _member_app(
        upload_document=UploadDocument(
            documents,
            InMemoryDocumentBytes(),
            CeleryDocumentJobQueue(),
            1024,
        )
    )
    headers, token = _auth(jwt_service, user_id, tenant_id)
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("handbook.pdf", b"%PDF-1.4 minimal", "application/pdf")},
    )

    assert response.status_code == 201
    document_id = response.json()["data"]["id"]
    logs = _ops(capops)
    assert len(logs) == 1
    assert logs[0]["route"] == "POST /api/v1/documents"
    assert logs[0]["tenant_id"] == tenant_id
    assert logs[0]["status_code"] == 201
    correlation_id = logs[0]["correlation_id"]
    assert sent["name"] == "app.infrastructure.worker.tasks.process_document"
    assert sent["kwargs"] == {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "document_id": document_id,
    }
    assert sent["headers"] == {CORRELATION_HEADER: correlation_id}
    assert CORRELATION_HEADER == "ai_rag_correlation_id"
    assert token not in capops.text
    assert "%PDF" not in capops.text
    assert user_id not in capops.text


def test_enqueue_outside_a_request_omits_the_header(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent["kwargs"] = kwargs.get("kwargs")
        sent["headers"] = kwargs.get("headers")

    monkeypatch.setattr(
        "app.infrastructure.worker.document_job_queue.celery_app.send_task",
        fake_send_task,
    )
    CeleryDocumentJobQueue().enqueue(tenant_id="t1", user_id="u1", document_id="d1")
    assert sent["kwargs"] == {"tenant_id": "t1", "user_id": "u1", "document_id": "d1"}
    assert sent["headers"] is None


def test_finished_job_logs_ready_or_failed(capops: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = iter((ProcessOutcome.READY, ProcessOutcome.FAILED))

    def build() -> _Outcome:
        return _Outcome(next(outcomes))

    monkeypatch.setattr("app.bootstrap.worker.build_process_document", build)

    with _pushed({CORRELATION_HEADER: "cid-ready"}):
        process_document.run("tenant-ready", "user-ready", "doc-ready")
    with _pushed({CORRELATION_HEADER: "cid-failed"}):
        process_document.run("tenant-failed", "user-failed", "doc-failed")

    assert _ops(capops) == [
        {
            "event": "ingestion.job",
            "correlation_id": "cid-ready",
            "tenant_id": "tenant-ready",
            "document_id": "doc-ready",
            "status": "ready",
        },
        {
            "event": "ingestion.job",
            "correlation_id": "cid-failed",
            "tenant_id": "tenant-failed",
            "document_id": "doc-failed",
            "status": "failed",
        },
    ]
    assert "user-ready" not in capops.text
    assert "user-failed" not in capops.text
    for record in _ops(capops):
        assert set(record) == _JOB_KEYS


def test_deferred_skipped_and_missing_header(
    capops: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = ProcessOutcome.DEFERRED

    class Runner:
        def execute(self, actor: object, document_id: str) -> ProcessOutcome:
            return outcome

    monkeypatch.setattr("app.bootstrap.worker.build_process_document", lambda: Runner())
    countdowns: list[int] = []

    def fake_retry(*_args: object, countdown: int | None = None, **_kwargs: object) -> None:
        if countdown is not None:
            countdowns.append(countdown)
        raise RuntimeError("retry")

    monkeypatch.setattr(process_document, "retry", fake_retry)
    with _pushed({CORRELATION_HEADER: "cid-defer"}), pytest.raises(RuntimeError, match="retry"):
        process_document.run("t1", "u1", "doc-defer")
    assert countdowns == [5]
    assert _ops(capops) == []

    outcome = ProcessOutcome.SKIPPED
    with _pushed({CORRELATION_HEADER: "cid-skip"}):
        process_document.run("t1", "u1", "doc-skip")
    assert _ops(capops) == []

    outcome = ProcessOutcome.READY
    with _pushed(None):
        assert process_document.request.headers is None
        process_document.run("tenant-open", "user-open", "doc-open")
    logs = _ops(capops)
    assert logs == [
        {
            "event": "ingestion.job",
            "correlation_id": None,
            "tenant_id": "tenant-open",
            "document_id": "doc-open",
            "status": "ready",
        }
    ]
    assert "user-open" not in capops.text


def test_retry_options_keep_the_correlation_header() -> None:
    with _pushed({CORRELATION_HEADER: "cid-keep"}):
        signature = process_document.signature_from_request(countdown=5)
    assert signature.options["headers"] == {CORRELATION_HEADER: "cid-keep"}
    assert signature.options["countdown"] == 5
    assert "correlation_id" not in signature.options["headers"]


def test_exception_before_outcome_does_not_log(
    capops: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.bootstrap.worker.build_process_document",
        lambda: _Boom(),
    )
    with _pushed({CORRELATION_HEADER: "cid-boom"}), pytest.raises(RuntimeError, match="secret-exception"):
        process_document.run("t1", "u1", "doc-boom")
    assert _ops(capops) == []


def test_stderr_handler_only_when_root_has_no_handlers() -> None:
    tenants = InMemoryTenantRepository()
    users = InMemoryUserRepository()
    hasher = FakePasswordHasher()
    BootstrapTenant(tenants, users, hasher).execute(
        BootstrapCommand(tenant_name="Demo", admin_email=_EMAIL, admin_password=_PASSWORD)
    )
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    try:
        create_app(
            settings=Settings(jwt_secret=_SECRET),
            readiness_probes=[],
            login=Login(users, hasher),
            get_current_member=GetCurrentMember(users),
            jwt_service=JwtService(_SECRET),
        )
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stderr
        assert handler.formatter is not None
        assert handler.formatter._fmt == "%(message)s"  # type: ignore[attr-defined]
    finally:
        root.handlers[:] = saved


def test_domain_and_application_do_not_import_a_logging_sdk() -> None:
    import app.application
    import app.domain

    banned = (
        "import logging",
        "from logging",
        "import structlog",
        "from structlog",
        "import loguru",
        "from loguru",
    )
    roots = (
        Path(app.domain.__file__).resolve().parent,
        Path(app.application.__file__).resolve().parent,
    )
    for root in roots:
        for path in root.rglob("*.py"):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                assert not stripped.startswith(banned), f"{path}: {stripped}"
