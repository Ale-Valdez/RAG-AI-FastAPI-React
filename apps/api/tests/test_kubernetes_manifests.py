from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST_DIR = _REPO_ROOT / "deploy" / "kubernetes"
_IMAGE = "image: ai-rag-api:latest"
_WORKER_IMAGE = "image: ai-rag-worker:latest"
_CELERY_COMMAND = """          command:
            - celery
            - -A
            - app.infrastructure.worker.celery_app:celery_app
            - worker
            - --loglevel=INFO
            - --concurrency=1
            - --max-tasks-per-child=1
"""
_MIGRATE_COMMAND = """          command:
            - alembic
            - upgrade
            - head
"""


def _manifests() -> dict[str, str]:
    return {path.name: path.read_text() for path in sorted(_MANIFEST_DIR.glob("*.yaml"))}


def test_kubernetes_manifests_share_image_secret_and_amazon_s3() -> None:
    manifests = _manifests()
    assert set(manifests) == {
        "api.yaml",
        "migrate-job.yaml",
        "namespace.yaml",
        "secret.yaml",
        "worker.yaml",
    }
    images = [
        line.strip()
        for text in manifests.values()
        for line in text.splitlines()
        if line.strip().startswith("image:")
    ]
    assert images == [_IMAGE, _IMAGE, _WORKER_IMAGE]

    assert "kind: Namespace" in manifests["namespace.yaml"]
    assert "name: ai-rag" in manifests["namespace.yaml"]

    secret = manifests["secret.yaml"]
    assert "name: ai-rag-env" in secret
    assert "namespace: ai-rag" in secret
    assert (
        'DATABASE_URL: "postgresql://app:REPLACE_ME@postgres.example:5432/app?sslmode=require"'
        in secret
    )
    assert 'REDIS_URL: "redis://redis.example:6379/0"' in secret
    assert 'QDRANT_URL: "http://qdrant.example:6333"' in secret
    assert "selector:\n    app: api" in manifests["api.yaml"]
    assert 'S3_ENDPOINT_URL: ""' in secret
    assert 'S3_REGION: "us-east-1"' in secret
    assert 'S3_USE_PATH_STYLE: "false"' in secret
    assert 'S3_BUCKET: "ai-rag-documents"' in secret
    assert 'S3_ACCESS_KEY_ID: "REPLACE_ME"' in secret
    assert 'S3_SECRET_ACCESS_KEY: "REPLACE_ME"' in secret
    assert 'JWT_SECRET: ""' in secret
    assert "GK0123456789abcdef0123456789abcd" not in secret

    for name in ("api.yaml", "migrate-job.yaml", "worker.yaml"):
        text = manifests[name]
        assert "namespace: ai-rag" in text
        assert "envFrom:" in text
        assert "secretRef:" in text
        assert "name: ai-rag-env" in text
        if name == "worker.yaml":
            assert _WORKER_IMAGE in text
            assert "DOCLING_ARTIFACTS_PATH" in text
            assert "/opt/docling/models" in text
        else:
            assert _IMAGE in text


def test_kubernetes_api_probes_worker_celery_and_migrate_job() -> None:
    manifests = _manifests()
    api = manifests["api.yaml"]
    worker = manifests["worker.yaml"]
    job = manifests["migrate-job.yaml"]

    assert "kind: Deployment" in api
    assert "kind: Service" in api
    assert "name: api" in api
    assert "containerPort: 8000" in api
    assert "port: 8000" in api
    assert "targetPort: 8000" in api
    assert "livenessProbe:" in api
    assert "path: /api/health" in api
    assert "readinessProbe:" in api
    assert "path: /api/ready" in api
    assert "command:" not in api
    probe_paths = [line.strip() for line in api.splitlines() if line.strip().startswith("path:")]
    assert probe_paths == ["path: /api/health", "path: /api/ready"]

    assert "name: worker" in worker
    assert _CELERY_COMMAND in worker
    assert "livenessProbe" not in worker
    assert "readinessProbe" not in worker
    assert "/api/health" not in worker
    assert "/api/ready" not in worker

    assert "kind: Job" in job
    assert "name: ai-rag-migrate" in job
    assert "restartPolicy: Never" in job
    assert _MIGRATE_COMMAND in job

    combined = "\n".join(manifests.values())
    assert "kind: Ingress" not in combined
    assert "postgres:16" not in combined
    assert "redis:7" not in combined
    assert "qdrant/qdrant" not in combined
    assert "dxflrs/garage" not in combined
    assert "name: web" not in combined


def test_compose_keeps_garage_s3_and_celery_command() -> None:
    compose = (_REPO_ROOT / "compose.yaml").read_text()
    assert "image: dxflrs/garage:v2.4.1" in compose
    assert "S3_ENDPOINT_URL: http://garage:3900" in compose
    assert "S3_REGION: garage" in compose
    assert 'S3_USE_PATH_STYLE: "true"' in compose
    assert (
        "command: celery -A app.infrastructure.worker.celery_app:celery_app worker --loglevel=INFO --concurrency=1 --max-tasks-per-child=1"
        in compose
    )
    assert "target: api" in compose
    assert "target: worker" in compose
    assert "DOCLING_ARTIFACTS_PATH: /opt/docling/models" in compose
