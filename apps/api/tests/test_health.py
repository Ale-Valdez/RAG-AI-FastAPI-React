from app.application.health.get_health import GetHealth
from app.application.health.get_readiness import GetReadiness
from app.bootstrap.create_app import create_app
from app.infrastructure.config.settings import Settings
from fastapi.testclient import TestClient

_TEST_SETTINGS = Settings(jwt_secret="test-secret-key-at-least-32-bytes!!")


class FakeProbe:
    def __init__(self, name: str, ok: bool) -> None:
        self.name = name
        self._ok = ok

    async def check(self) -> bool:
        return self._ok


def test_get_health_use_case() -> None:
    result = GetHealth("demo").execute()
    assert result.status == "ok"
    assert result.service == "demo"


async def test_get_readiness_use_case() -> None:
    ready = await GetReadiness([FakeProbe("redis", True), FakeProbe("qdrant", False)]).execute()
    assert ready.status == "unavailable"
    assert ready.probes[1].ok is False


def test_health_endpoint() -> None:
    client = TestClient(create_app(settings=_TEST_SETTINGS, readiness_probes=[]))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_endpoint_ok() -> None:
    client = TestClient(
        create_app(settings=_TEST_SETTINGS, readiness_probes=[FakeProbe("redis", True)])
    )
    response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_endpoint_unavailable() -> None:
    client = TestClient(
        create_app(settings=_TEST_SETTINGS, readiness_probes=[FakeProbe("postgres", False)])
    )
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
